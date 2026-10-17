"""DAG-based task graph for tracking dependencies and execution order."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskState(str, Enum):
    PENDING = "pending"
    READY = "ready"       # All dependencies met, can be scheduled
    RUNNING = "running"
    REVIEW = "review"
    APPROVED = "approved"
    MERGED = "merged"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass
class TaskNode:
    """A task in the dependency graph."""

    task_id: str
    title: str
    subsystem: str
    assigned_to: str  # Agent role
    priority: int = 3
    state: TaskState = TaskState.PENDING
    dependencies: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    assigned_agent_id: str | None = None
    review_rounds: int = 0

    @property
    def is_terminal(self) -> bool:
        return self.state in (TaskState.MERGED, TaskState.FAILED)


class TaskGraph:
    """Directed acyclic graph of tasks with dependency tracking.

    Tasks can only execute when all their dependencies are in a terminal
    success state (MERGED). The graph supports topological ordering for
    scheduling and can detect cycles.
    """

    def __init__(self):
        self._nodes: dict[str, TaskNode] = {}
        self._dependents: dict[str, set[str]] = defaultdict(set)  # task -> tasks that depend on it

    def add_task(self, task: dict[str, Any]) -> TaskNode:
        """Add a task to the graph."""
        node = TaskNode(
            task_id=task["task_id"],
            title=task["title"],
            subsystem=task.get("subsystem") or "unknown",
            # `or`, not a .get default: the manager emits the key with a null
            # value when the model omits a role, and .get(k, default) returns
            # that None rather than the default. assigned_to=None then matches
            # no agent in scheduler.get_assignments, so the task sits "ready"
            # forever and the loop spins until the iteration cap with no work
            # done and no error raised.
            assigned_to=task.get("assigned_to") or "developer",
            priority=task.get("priority") or 3,
            dependencies=task.get("dependencies") or [],
            data=task,
        )
        self._nodes[node.task_id] = node

        # Track reverse dependencies
        for dep_id in node.dependencies:
            self._dependents[dep_id].add(node.task_id)

        # Check if task is immediately ready
        self._update_readiness(node)
        return node

    def add_tasks(self, tasks: list[dict[str, Any]]) -> list[TaskNode]:
        """Add multiple tasks at once."""
        nodes = [self.add_task(t) for t in tasks]
        # Re-check readiness after all tasks added
        for node in nodes:
            self._update_readiness(node)
        return nodes

    def get_ready_tasks(self) -> list[TaskNode]:
        """Get all tasks that are ready to execute (dependencies met).

        Returns tasks sorted by priority (lower = higher priority).
        """
        ready = [n for n in self._nodes.values() if n.state == TaskState.READY]
        return sorted(ready, key=lambda n: n.priority)

    def get_tasks_by_state(self, state: TaskState) -> list[TaskNode]:
        """Get all tasks in a given state."""
        return [n for n in self._nodes.values() if n.state == state]

    def update_state(self, task_id: str, new_state: TaskState) -> None:
        """Update a task's state and cascade readiness checks."""
        if task_id not in self._nodes:
            raise KeyError(f"Unknown task: {task_id}")

        node = self._nodes[task_id]
        old_state = node.state
        node.state = new_state

        # When a task completes, check if dependents are now ready
        if new_state == TaskState.MERGED:
            for dep_id in self._dependents.get(task_id, set()):
                if dep_id in self._nodes:
                    self._update_readiness(self._nodes[dep_id])

    def requeue(self, task_id: str, feedback: dict[str, Any]) -> TaskNode:
        """Return a rejected task to its author with the review attached.

        A rejection used to set BLOCKED, which nothing ever left: one bad review
        halted a linear chain for the rest of the run (w11 F6 and V8). The
        feedback travels in `data` because that is what the author's prompt is
        built from; a retry that cannot see why it was rejected retries blind.
        """
        node = self._nodes[task_id]
        node.review_rounds += 1
        node.data.setdefault("review_feedback", []).append(feedback)
        node.state = TaskState.READY
        return node

    def fail(self, task_id: str, reason: str) -> None:
        """Terminal failure that says why. `Orchestration failed: unknown` was
        the only thing either w11 run reported."""
        node = self._nodes[task_id]
        node.data["failure_reason"] = reason
        node.state = TaskState.FAILED

    def assign_agent(self, task_id: str, agent_id: str) -> None:
        """Record which agent is working on a task."""
        self._nodes[task_id].assigned_agent_id = agent_id
        self._nodes[task_id].state = TaskState.RUNNING

    def to_dict(self) -> list[dict[str, Any]]:
        """Every node, as JSON-safe data. Persisted each iteration so a run cut
        off by its time budget can resume without re-planning (w17)."""
        return [{
            "task_id": n.task_id,
            "title": n.title,
            "subsystem": n.subsystem,
            "assigned_to": n.assigned_to,
            "priority": n.priority,
            "state": n.state.value,
            "dependencies": list(n.dependencies),
            "data": n.data,
            "assigned_agent_id": n.assigned_agent_id,
            "review_rounds": n.review_rounds,
        } for n in self._nodes.values()]

    @classmethod
    def from_dict(cls, nodes: list[dict[str, Any]]) -> TaskGraph:
        graph = cls()
        graph.load_nodes(nodes)
        return graph

    def load_nodes(self, nodes: list[dict[str, Any]]) -> None:
        """Replace this graph's contents with saved nodes, states included.

        In place rather than a new graph, because the scheduler holds a
        reference to this one.
        """
        self._nodes.clear()
        self._dependents.clear()
        for raw in nodes:
            node = TaskNode(
                task_id=raw["task_id"],
                title=raw["title"],
                subsystem=raw["subsystem"],
                assigned_to=raw["assigned_to"],
                priority=raw.get("priority", 3),
                state=TaskState(raw["state"]),
                dependencies=list(raw.get("dependencies") or []),
                data=dict(raw.get("data") or {}),
                assigned_agent_id=raw.get("assigned_agent_id"),
                review_rounds=raw.get("review_rounds", 0),
            )
            self._nodes[node.task_id] = node
            for dep_id in node.dependencies:
                self._dependents[dep_id].add(node.task_id)
        for node in self._nodes.values():
            self._update_readiness(node)

    def get_task(self, task_id: str) -> TaskNode | None:
        return self._nodes.get(task_id)

    @property
    def all_tasks(self) -> list[TaskNode]:
        return list(self._nodes.values())

    @property
    def is_complete(self) -> bool:
        """True if all tasks are in a terminal state."""
        return all(n.is_terminal for n in self._nodes.values())

    @property
    def progress(self) -> dict[str, int]:
        """Count of tasks in each state."""
        counts: dict[str, int] = {}
        for node in self._nodes.values():
            counts[node.state.value] = counts.get(node.state.value, 0) + 1
        return counts

    def topological_order(self) -> list[str]:
        """Return task IDs in dependency order (topological sort)."""
        in_degree: dict[str, int] = {tid: 0 for tid in self._nodes}
        for node in self._nodes.values():
            for dep in node.dependencies:
                if dep in in_degree:
                    in_degree[node.task_id] += 1

        queue = deque(tid for tid, deg in in_degree.items() if deg == 0)
        order = []

        while queue:
            tid = queue.popleft()
            order.append(tid)
            for dependent_id in self._dependents.get(tid, set()):
                if dependent_id in in_degree:
                    in_degree[dependent_id] -= 1
                    if in_degree[dependent_id] == 0:
                        queue.append(dependent_id)

        if len(order) != len(self._nodes):
            missing = set(self._nodes.keys()) - set(order)
            raise ValueError(f"Cycle detected in task graph. Involved tasks: {missing}")

        return order

    def _update_readiness(self, node: TaskNode) -> None:
        """Check if a task's dependencies are met and mark it ready."""
        if node.state != TaskState.PENDING:
            return

        # Check all dependencies
        for dep_id in node.dependencies:
            dep = self._nodes.get(dep_id)
            if dep is None:
                # Dependency on unknown task - treat as unmet
                return
            if dep.state != TaskState.MERGED:
                return

        # All dependencies met
        node.state = TaskState.READY

    def create_slm_training_tasks(self, goal: str) -> list[dict[str, Any]]:
        """The SLM pipeline the kernel actually ships (SLM/DATA.md), as tasks.

        Ground-truth corpora within the kernel tokenizer's budget -> config ->
        train -> evaluate, export to the AUTON format, parity with the in-kernel
        forward pass and the chat eval -> int8 only if it holds -> placed where
        the kernel build boots it. Every task names what it produces.
        """
        def task(task_id, title, assigned_to, deps, priority, produces, description, criteria):
            return {"task_id": task_id, "title": title, "subsystem": "slm",
                    "assigned_to": assigned_to, "dependencies": deps, "priority": priority,
                    "produces": produces, "description": description,
                    "acceptance_criteria": criteria, "spec_reference": "SLM/DATA.md"}

        return [
            task("slm-data-prep", "Build the kernel training set from ground truth",
                 "data_scientist", [], 1,
                 ["slm/data/os_chat.jsonl", "slm/data/hardware_kernel.jsonl",
                  "slm/work/vocab.json", "slm/work/tokens.jsonl"],
                 f"Goal: {goal}. build_corpus into slm/data; check_vocab_budget on both files "
                 "as one set; tokenize_data with vocab_size 1024 to slm/work/vocab.json and "
                 "slm/work/tokens.jsonl.",
                 ["check_vocab_budget reports 0% answer <unk>", "no answer written by hand"]),
            task("slm-arch-design", "Choose the model configuration", "model_architect", [], 1,
                 ["slm/config.yaml"],
                 "Start from SLM/configs/chat_tiny.yaml; copy it to slm/config.yaml, changing it "
                 "only for a measured reason. validate_architecture and estimate_flops.",
                 ["vocab_size <= 1024", "fits the boot memory budget, or int8 is planned"]),
            task("slm-training", "Train the model", "training",
                 ["slm-data-prep", "slm-arch-design"], 2, ["slm/work/final.pt"],
                 "train_model with slm/config.yaml on slm/work/tokens.jsonl, output slm/work.",
                 ["training loss decreases", "a final checkpoint exists"]),
            task("slm-evaluation", "Evaluate: parity and the chat eval", "training",
                 ["slm-training"], 3, ["slm/work/auton-slm-fp32.bin", "slm/eval/fp32.json"],
                 "evaluate_model for held-out loss; export_auton (fp32) to "
                 "slm/work/auton-slm-fp32.bin; run_parity; run_chat_eval with json_path "
                 "slm/eval/fp32.json.",
                 ["run_parity exits 0", "chat eval >= 70% correct-or-honest and < 10% garbage, "
                  "or the shortfall reported as measured"]),
            task("slm-quantization", "Try int8, keep it only if it holds", "training",
                 ["slm-evaluation"], 4, ["slm/work/auton-slm-int8.bin", "slm/eval/int8.json"],
                 "export_auton with quant int8; run_parity; run_chat_eval. Keep int8 only if parity "
                 "passes and the chat score does not fall.",
                 ["the choice between fp32 and int8 is stated with both scores"]),
            task("slm-export", "Export the chosen model", "training", ["slm-quantization"], 5,
                 ["slm/export/auton-slm.bin"],
                 "Copy the chosen AUTON-format model and its manifest to slm/export/. GGUF/ONNX "
                 "only if asked for host tools.",
                 ["the file loads as MODEL_FORMAT_AUTON"]),
            task("slm-integration", "Place the model where the kernel boots it", "integrator",
                 ["slm-export"], 6, ["models/auton-slm.bin"],
                 "integrate_slm with slm/export/auton-slm.bin; the kernel boots it with "
                 "`make iso-neural MODEL=models/auton-slm.bin`.",
                 ["the boot log shows [SLM] Backend: neural"]),
        ]
