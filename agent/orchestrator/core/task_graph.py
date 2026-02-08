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
            subsystem=task.get("subsystem", "unknown"),
            assigned_to=task.get("assigned_to", "developer"),
            priority=task.get("priority", 3),
            dependencies=task.get("dependencies", []),
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

    def assign_agent(self, task_id: str, agent_id: str) -> None:
        """Record which agent is working on a task."""
        self._nodes[task_id].assigned_agent_id = agent_id
        self._nodes[task_id].state = TaskState.RUNNING

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
        """Create task graph for SLM training workflow."""
        tasks = []

        # 1. Data Preparation
        tasks.append({
            "task_id": "slm-data-prep",
            "title": "Prepare SLM training dataset",
            "description": "Clean, tokenize, and split dataset",
            "subsystem": "slm",
            "assigned_to": "data_scientist",
            "dependencies": [],
            "priority": 1,
        })

        # 2. Architecture Design
        tasks.append({
            "task_id": "slm-arch-design",
            "title": "Design SLM architecture",
            "description": "Create model config YAML, estimate FLOPs",
            "subsystem": "slm",
            "assigned_to": "model_architect",
            "dependencies": [],
            "priority": 1,
        })

        # 3. Training
        tasks.append({
            "task_id": "slm-training",
            "title": "Train SLM model",
            "description": "Execute training loop, save checkpoints",
            "subsystem": "slm",
            "assigned_to": "training",
            "dependencies": ["slm-data-prep", "slm-arch-design"],
            "priority": 2,
        })

        # 4. Evaluation
        tasks.append({
            "task_id": "slm-evaluation",
            "title": "Evaluate trained model",
            "description": "Run benchmarks, select best checkpoint",
            "subsystem": "slm",
            "assigned_to": "training",
            "dependencies": ["slm-training"],
            "priority": 3,
        })

        # 5. Quantization
        tasks.append({
            "task_id": "slm-quantization",
            "title": "Quantize SLM to INT4",
            "description": "Compress model using GPTQ",
            "subsystem": "slm",
            "assigned_to": "training",
            "dependencies": ["slm-evaluation"],
            "priority": 4,
        })

        # 6. Export
        tasks.append({
            "task_id": "slm-export",
            "title": "Export SLM to GGUF",
            "description": "Convert to GGUF format, validate",
            "subsystem": "slm",
            "assigned_to": "training",
            "dependencies": ["slm-quantization"],
            "priority": 5,
        })

        # 7. Integration
        tasks.append({
            "task_id": "slm-integration",
            "title": "Integrate SLM into kernel",
            "description": "Copy to kernel workspace, update Makefile, test",
            "subsystem": "slm",
            "assigned_to": "integrator",
            "dependencies": ["slm-export"],
            "priority": 6,
        })

        return tasks
