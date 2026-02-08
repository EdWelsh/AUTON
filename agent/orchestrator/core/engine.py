"""Main orchestration engine - the VibeTensor-style iterative build loop."""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from orchestrator.agents.architect_agent import ArchitectAgent
from orchestrator.agents.base_agent import AgentRole, TaskResult
from orchestrator.agents.data_scientist_agent import DataScientistAgent
from orchestrator.agents.developer_agent import DeveloperAgent
from orchestrator.agents.integrator_agent import IntegratorAgent
from orchestrator.agents.manager_agent import ManagerAgent
from orchestrator.agents.model_architect_agent import ModelArchitectAgent
from orchestrator.agents.reviewer_agent import ReviewerAgent
from orchestrator.agents.tester_agent import TesterAgent
from orchestrator.agents.training_agent import TrainingAgent
from orchestrator.comms.git_workspace import GitWorkspace
from orchestrator.comms.message_bus import MessageBus
from orchestrator.core.scheduler import Scheduler
from orchestrator.core.state import OrchestratorState
from orchestrator.core.task_graph import TaskGraph, TaskState
from orchestrator.arch_registry import ArchProfile, get_arch_profile
from orchestrator.llm.client import CostTracker, LLMClient, ProviderConfig

logger = logging.getLogger(__name__)


class WorkflowMode(str, Enum):
    """Orchestration workflow modes."""
    KERNEL_BUILD = "kernel_build"
    SLM_TRAINING = "slm_training"
    DUAL = "dual"


class OrchestrationEngine:
    """The main engine that runs the VibeTensor-style iterative build loop.

    Loop:
    1. Manager decomposes goal into tasks
    2. Architect designs subsystem interfaces
    3. Developers implement code in parallel on feature branches
    4. Reviewers validate proposed changes
    5. Testers run builds and test suites
    6. Integrator merges approved branches
    7. Repeat until all tasks are complete or budget exhausted

    This is the "specify goals -> decompose -> agents generate diffs ->
    validate (build + test) -> accept/reject -> broaden scope" cycle.
    """

    def __init__(
        self,
        workspace_path: Path,
        kernel_spec_path: Path,
        config: dict[str, Any],
    ):
        self.workspace_path = workspace_path
        self.kernel_spec_path = kernel_spec_path
        self.config = config

        # Load architecture profile
        kernel_config = config.get("kernel", {})
        arch_name = kernel_config.get("arch", "x86_64")
        self.arch_profile: ArchProfile = get_arch_profile(arch_name)
        logger.info("Target architecture: %s", self.arch_profile.display_name)

        # Workflow mode
        self.workflow_mode = WorkflowMode(
            self.config.get("workflow", {}).get("mode", "kernel_build")
        )
        logger.info("Workflow mode: %s", self.workflow_mode.value)

        # Core components
        llm_config = config.get("llm", {})
        self.cost_tracker = CostTracker(
            max_cost_usd=llm_config.get("cost", {}).get("max_cost_usd", 50.0),
            warn_at_usd=llm_config.get("cost", {}).get("warn_at_usd", 25.0),
        )
        provider_config = ProviderConfig(
            api_keys=dict(llm_config.get("api_keys", {})),
            endpoints=dict(llm_config.get("endpoints", {})),
        )
        # Backward compat: old single api_key field maps to anthropic
        if "api_key" in llm_config and "anthropic" not in provider_config.api_keys:
            provider_config.api_keys["anthropic"] = llm_config["api_key"]

        self.client = LLMClient(
            model=llm_config.get("model", "anthropic/claude-opus-4-6"),
            max_tokens=llm_config.get("max_tokens", 16384),
            provider_config=provider_config,
            cost_tracker=self.cost_tracker,
        )
        self.workspace = GitWorkspace(
            workspace_path=workspace_path,
            branch_prefix=config.get("workspace", {}).get("branch_prefix", "agent"),
        )
        self.message_bus = MessageBus(workspace_path)
        self.task_graph = TaskGraph()
        self.scheduler = Scheduler(self.task_graph)

        # State
        self.state: OrchestratorState | None = None
        self._agents: dict[str, Any] = {}

    def _create_agent(self, agent_id: str, role: AgentRole, cls: type) -> Any:
        """Create an agent instance with architecture awareness."""
        model_overrides = self.config.get("agents", {}).get("models", {})
        return cls(
            agent_id=agent_id,
            client=self.client,
            workspace=self.workspace,
            message_bus=self.message_bus,
            kernel_spec_path=self.kernel_spec_path,
            model_override=model_overrides.get(role.value),
            arch_profile=self.arch_profile,
        )

    def _init_agents(self) -> None:
        """Create all agent instances and register them with the scheduler."""
        agent_config = self.config.get("agents", {})

        # Single-instance agents
        self._agents["manager"] = self._create_agent(
            "manager-01", AgentRole.MANAGER, ManagerAgent
        )
        self._agents["architect"] = self._create_agent(
            "architect-01", AgentRole.ARCHITECT, ArchitectAgent
        )
        self._agents["integrator"] = self._create_agent(
            "integrator-01", AgentRole.INTEGRATOR, IntegratorAgent
        )
        self.scheduler.register_agent("integrator", self._agents["integrator"])

        # Multi-instance agents
        dev_count = agent_config.get("developer_count", 4)
        for i in range(dev_count):
            agent = self._create_agent(
                f"dev-{i+1:02d}", AgentRole.DEVELOPER, DeveloperAgent
            )
            self._agents[f"dev-{i+1:02d}"] = agent
            self.scheduler.register_agent("developer", agent)

        reviewer_count = agent_config.get("reviewer_count", 1)
        for i in range(reviewer_count):
            agent = self._create_agent(
                f"reviewer-{i+1:02d}", AgentRole.REVIEWER, ReviewerAgent
            )
            self._agents[f"reviewer-{i+1:02d}"] = agent
            self.scheduler.register_agent("reviewer", agent)

        tester_count = agent_config.get("tester_count", 1)
        for i in range(tester_count):
            agent = self._create_agent(
                f"tester-{i+1:02d}", AgentRole.TESTER, TesterAgent
            )
            self._agents[f"tester-{i+1:02d}"] = agent
            self.scheduler.register_agent("tester", agent)

        logger.info(
            "Initialized %d agents: 1 manager, 1 architect, %d devs, "
            "%d reviewers, %d testers, 1 integrator",
            len(self._agents), dev_count, reviewer_count, tester_count,
        )

        # SLM agents (created if mode is slm_training or dual)
        if self.workflow_mode in [WorkflowMode.SLM_TRAINING, WorkflowMode.DUAL]:
            # Data Scientist
            self._agents["data_scientist"] = self._create_agent(
                "data-scientist-01", AgentRole.DATA_SCIENTIST, DataScientistAgent
            )
            self.scheduler.register_agent("data_scientist", self._agents["data_scientist"])

            # Model Architect
            self._agents["model_architect"] = self._create_agent(
                "model-architect-01", AgentRole.MODEL_ARCHITECT, ModelArchitectAgent
            )
            self.scheduler.register_agent("model_architect", self._agents["model_architect"])

            # Training Agents (parallel)
            training_count = agent_config.get("training_agent_count", 2)
            for i in range(training_count):
                agent = self._create_agent(
                    f"training-{i+1:02d}", AgentRole.TRAINING, TrainingAgent
                )
                self._agents[f"training-{i+1:02d}"] = agent
                self.scheduler.register_agent("training", agent)

            logger.info(
                "Initialized SLM agents: 1 data scientist, 1 model architect, %d training",
                training_count,
            )

    async def run(self, goal: str) -> dict[str, Any]:
        """Run the full orchestration loop for a goal.

        This is the main entry point. It runs until all tasks are
        complete, the budget is exhausted, or max iterations are reached.
        """
        run_id = uuid.uuid4().hex[:8]
        state_path = self.workspace_path / ".auton" / "state.json"
        self.state = OrchestratorState.load_or_create(state_path, run_id, goal)

        logger.info("=== AUTON Orchestration Run %s ===", run_id)
        logger.info("Goal: %s", goal)

        # Initialize workspace and agents
        self.workspace.init()
        self._init_agents()

        try:
            # Phase 1: Manager decomposes the goal into tasks
            self.state.phase = "planning"
            self.state.save(state_path)
            logger.info("--- Phase 1: Planning ---")

            # Create task graph based on workflow mode
            if self.workflow_mode == WorkflowMode.KERNEL_BUILD:
                # Existing kernel build workflow
                manager: ManagerAgent = self._agents["manager"]
                tasks = await manager.decompose_goal(goal)
            elif self.workflow_mode == WorkflowMode.SLM_TRAINING:
                # SLM training workflow only
                tasks = self.task_graph.create_slm_training_tasks(goal)
            elif self.workflow_mode == WorkflowMode.DUAL:
                # Both kernel and SLM tasks
                manager: ManagerAgent = self._agents["manager"]
                kernel_tasks = await manager.decompose_goal(goal)
                slm_tasks = self.task_graph.create_slm_training_tasks(goal)
                tasks = kernel_tasks + slm_tasks
            else:
                return {"success": False, "error": f"Unknown workflow mode: {self.workflow_mode}"}

            self.state.tasks_created = len(tasks)

            if not tasks:
                return {"success": False, "error": "Manager produced no tasks"}

            # Add tasks to the graph
            self.task_graph.add_tasks(tasks)
            logger.info("Task graph: %d tasks, order: %s",
                        len(tasks), self.task_graph.topological_order())

            # Phase 2: Architect designs interfaces for each subsystem
            self.state.phase = "designing"
            self.state.save(state_path)
            logger.info("--- Phase 2: Design ---")

            architect: ArchitectAgent = self._agents["architect"]
            subsystems = sorted(set(t.get("subsystem", "") for t in tasks if t.get("subsystem")))
            for subsystem in subsystems:
                await architect.design_subsystem(subsystem)
                self.workspace.checkout_main()

            # Phase 3: Development loop
            self.state.phase = "developing"
            self.state.save(state_path)
            logger.info("--- Phase 3: Development ---")

            max_iterations = 50
            for iteration in range(max_iterations):
                self.state.iteration = iteration
                self.state.total_cost_usd = self.cost_tracker.total_cost_usd
                self.state.save(state_path)

                if self.task_graph.is_complete:
                    logger.info("All tasks complete!")
                    break

                progress = self.task_graph.progress
                logger.info(
                    "Iteration %d | Progress: %s | Cost: $%.2f",
                    iteration, progress, self.cost_tracker.total_cost_usd,
                )

                # Get assignments and execute in parallel
                assignments = self.scheduler.get_assignments()
                if not assignments and self.scheduler.busy_count == 0:
                    # No tasks ready and no agents busy - might be blocked
                    logger.warning("No tasks schedulable and no agents busy. Checking for blocks.")
                    assessment = await manager.assess_progress()
                    logger.info("Manager assessment: %s", assessment)
                    if not self.task_graph.get_ready_tasks():
                        break

                # Execute assigned tasks in parallel
                if assignments:
                    results = await asyncio.gather(
                        *[
                            self._execute_agent_task(slot.agent, task_node)
                            for slot, task_node in assignments
                        ],
                        return_exceptions=True,
                    )

                    # Process results
                    for (slot, task_node), result in zip(assignments, results):
                        self.scheduler.release_agent(slot.agent.agent_id)

                        if isinstance(result, Exception):
                            logger.error("Agent %s failed: %s", slot.agent.agent_id, result)
                            self.task_graph.update_state(task_node.task_id, TaskState.FAILED)
                            self.state.tasks_failed += 1
                        elif isinstance(result, TaskResult) and result.success:
                            self.task_graph.update_state(task_node.task_id, TaskState.REVIEW)
                            # Trigger review
                            await self._trigger_review(task_node, result)
                        else:
                            self.task_graph.update_state(task_node.task_id, TaskState.BLOCKED)

                # Check for approved tasks to merge
                approved = self.task_graph.get_tasks_by_state(TaskState.APPROVED)
                if approved:
                    integrator: IntegratorAgent = self._agents["integrator"]
                    await integrator.merge_approved()
                    for task_node in approved:
                        if task_node.state == TaskState.MERGED:
                            self.state.tasks_completed += 1

                # Small delay to avoid tight loops
                await asyncio.sleep(1)

            # Phase 4: Final integration check
            self.state.phase = "integrating"
            self.state.save(state_path)
            logger.info("--- Phase 4: Final Integration ---")

            integrator = self._agents["integrator"]
            final_check = await integrator.full_integration_check()

            self.state.phase = "done"
            self.state.save(state_path)

            return {
                "success": self.task_graph.is_complete and final_check.get("success", False),
                "run_id": run_id,
                "progress": self.task_graph.progress,
                "total_cost_usd": self.cost_tracker.total_cost_usd,
                "iterations": self.state.iteration,
                "final_check": final_check,
            }

        except Exception as e:
            logger.exception("Orchestration failed: %s", e)
            self.state.phase = "error"
            self.state.save(state_path)
            return {"success": False, "error": str(e), "cost": self.cost_tracker.total_cost_usd}

    async def _execute_agent_task(self, agent: Any, task_node: Any) -> TaskResult:
        """Execute a task with the appropriate agent method."""
        self.workspace.checkout_main()  # Start from a clean state

        if hasattr(agent, "implement_task"):
            return await agent.implement_task(task_node.data)
        else:
            return await agent.execute_task(task_node.data)

    async def _trigger_review(self, task_node: Any, result: TaskResult) -> None:
        """Trigger a code review for a completed task."""
        if not result.branch:
            return

        reviewer_slot = self.scheduler.get_available_agent("reviewer")
        if reviewer_slot is None:
            logger.info("No reviewer available, task %s queued for review", task_node.task_id)
            return

        reviewer_slot.busy = True
        review_result = await reviewer_slot.agent.review_branch(
            task_node.task_id, result.branch
        )
        reviewer_slot.busy = False

        if review_result.get("verdict") == "approve":
            self.task_graph.update_state(task_node.task_id, TaskState.APPROVED)
        else:
            self.task_graph.update_state(task_node.task_id, TaskState.BLOCKED)
            # Send feedback to developer for fixes
            logger.info(
                "Review requested changes for %s: %s",
                task_node.task_id, review_result.get("summary"),
            )
