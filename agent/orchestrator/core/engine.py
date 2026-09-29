"""Main orchestration engine - the VibeTensor-style iterative build loop."""

from __future__ import annotations

import asyncio
import logging
import signal
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from orchestrator.agents.analyst_agent import AnalystAgent
from orchestrator.agents.architect_agent import ArchitectAgent
from orchestrator.agents.base_agent import AgentRole, TaskResult
from orchestrator.agents.data_scientist_agent import DataScientistAgent
from orchestrator.agents.developer_agent import DeveloperAgent
from orchestrator.agents.integrator_agent import IntegratorAgent
from orchestrator.agents.manager_agent import ManagerAgent
from orchestrator.agents.packager_agent import PackagerAgent
from orchestrator.agents.model_architect_agent import ModelArchitectAgent
from orchestrator.agents.reviewer_agent import ReviewerAgent
from orchestrator.agents.tester_agent import TesterAgent
from orchestrator.agents.training_agent import TrainingAgent
from orchestrator.comms.git_workspace import GitWorkspace, WorkspaceError
from orchestrator.comms.message_bus import MessageBus
from orchestrator.core import syntax_gate
from orchestrator.core.scheduler import Scheduler
from orchestrator.core.state import STATE_FORMAT, OrchestratorState
from orchestrator.core.task_graph import TaskGraph, TaskState
from orchestrator.arch_registry import ArchProfile, get_arch_profile
from orchestrator.llm.client import (
    DEFAULT_MAX_TOOL_TURNS,
    DEFAULT_REQUEST_TIMEOUT,
    CostTracker,
    LLMClient,
    ProviderConfig,
)
from orchestrator.validation import (
    BuildValidator,
    CompositionValidator,
    TestValidator,
)

logger = logging.getLogger(__name__)


# Roles whose tasks change the kernel tree, and so need its interfaces designed.
KERNEL_ROLES = ("developer", "tester", "architect")


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
        subject_path: Path | None = None,
        seed_tasks: list[dict[str, Any]] | None = None,
        manifest: dict[str, Any] | None = None,
        probe_path: Path | None = None,
    ):
        self.workspace_path = workspace_path
        self.kernel_spec_path = kernel_spec_path
        self.config = config
        # An existing application to analyse (application-to-environment).
        # Staged read-only into the workspace when the run starts.
        self.subject_path = Path(subject_path) if subject_path else None
        self.subject_hash = ""
        # Tasks a manifest handoff (A7) requires, each carrying its gate.
        self.seed_tasks = list(seed_tasks or [])
        # A manifest to package (A8). Written to .auton/manifest.json, where the
        # package gate reads it; its substrate decides whether a Packager runs.
        self.manifest = dict(manifest or {})
        # The operator's probe declaration (A10); kept outside the workspace,
        # where no agent can rewrite what "works" means.
        self.probe_path = Path(probe_path).resolve() if probe_path else None

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
            request_timeout=float(llm_config.get("request_timeout", DEFAULT_REQUEST_TIMEOUT)),
            max_tool_turns=int(llm_config.get("max_tool_turns", DEFAULT_MAX_TOOL_TURNS)),
        )
        self.workspace = GitWorkspace(
            workspace_path=workspace_path,
            branch_prefix=config.get("workspace", {}).get("branch_prefix", "agent"),
        )
        self.message_bus = MessageBus(workspace_path)
        self.task_graph = TaskGraph()
        self.scheduler = Scheduler(self.task_graph)

        # Validation layer. Agents build/test via shell tools during development,
        # but the engine independently verifies the final result here so success
        # is gated on a real build + QEMU boot, not just agent self-report.
        validation_config = config.get("validation", {})
        self.build_timeout = validation_config.get("build_timeout", 120)
        self.test_timeout = validation_config.get("test_timeout", 60)
        self.composition_checks = validation_config.get("composition_checks", True)
        self.build_validator = BuildValidator(
            workspace_path=workspace_path, arch_profile=self.arch_profile
        )
        self.test_validator = TestValidator(
            workspace_path=workspace_path,
            timeout=self.test_timeout,
            arch_profile=self.arch_profile,
        )
        self.composition_validator = CompositionValidator(workspace_path)

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
        # The architect must be SCHEDULABLE, not merely constructed. The
        # manager's prompt advertises "architect" as an assignable role
        # (manager_agent.py:70), so every design task it produced was routed to
        # an empty pool and silently never dispatched.
        self.scheduler.register_agent("architect", self._agents["architect"])
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
            agent.probe_path = getattr(self, "probe_path", None)
            self._agents[f"tester-{i+1:02d}"] = agent
            self.scheduler.register_agent("tester", agent)

        # The Analyst exists only when there is something to analyse, and is
        # registered AND advertised — all three, or tasks for it never run.
        if self.subject_path is not None:
            analyst = self._create_agent("analyst-01", AgentRole.ANALYST, AnalystAgent)
            analyst.subject_hash = self.subject_hash
            analyst.subject_commit = self.workspace.subject_commit
            analyst.subject_repo = str(self.subject_path)
            self._agents["analyst"] = analyst
            self.scheduler.register_agent("analyst", analyst)
            self._agents["manager"].advertise_role(
                "analyst",
                "- An existing application is staged read-only at .auton/subject/. "
                "Analysing it is ONE task, assigned_to \"analyst\", producing "
                "analysis/<application>.artifact.yaml.")

        substrate = (self.manifest.get("application") or {}).get("substrate")
        if substrate in ("docker", "kubernetes", "server"):
            packager = self._create_agent("packager-01", AgentRole.PACKAGER, PackagerAgent)
            packager.manifest = self.manifest
            self._agents["packager"] = packager
            self.scheduler.register_agent("packager", packager)
            self._agents["manager"].advertise_role(
                "packager",
                f"- The manifest's substrate is {substrate}. Packaging the application is "
                "ONE task, assigned_to \"packager\", producing package/Dockerfile and "
                "package/PROVENANCE.json.")

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

    async def run(self, goal: str, resume: bool = False) -> dict[str, Any]:
        """Run the full orchestration loop for a goal.

        This is the main entry point. It runs until all tasks are
        complete, the budget is exhausted, or max iterations are reached.

        SIGTERM or SIGINT pauses rather than kills: the work in flight is
        committed on its branch, the task graph is saved, and the result says
        `paused`. `resume=True` continues that run without re-planning (w17:
        R1 lost an uncommitted 13,982-byte pmm.c at its time budget).
        """
        state_path = self.workspace_path / ".auton" / "state.json"
        model = str(self.config.get("llm", {}).get("model", ""))

        # Initialize workspace first: a resume is checked against main's HEAD.
        self.workspace.init()
        if resume:
            refusal = self._resume_refusal(state_path, goal, model)
            if refusal:
                logger.error("Refusing to resume: %s", refusal)
                return {"success": False, "resume_refused": refusal,
                        "error": f"refusing to resume: {refusal}"}
            self.state = OrchestratorState.load(state_path)
            self.state.resume_count += 1
            # The check it guarded has passed. Cleared, because this session
            # will move main itself: if it is then killed rather than paused,
            # a stale value would refuse the next resume forever (w17 review).
            self.state.head_at_save = ""
        else:
            # A new run never inherits a saved one. load_or_create used to hand
            # a fresh run the previous run's id and goal.
            self.state = OrchestratorState(
                run_id=uuid.uuid4().hex[:8], goal=goal, model=model)
        self.state.save(state_path)

        if self.subject_path is not None:
            refusal = self._stage_subject(resume)
            if refusal:
                return {"success": False, "error": refusal,
                        **({"resume_refused": refusal} if resume else {})}
            self.state.save(state_path)

        if getattr(self, "manifest", None):
            import json as _json
            target = self.workspace_path / ".auton" / "manifest.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_json.dumps(self.manifest, indent=2) + "\n")

        logger.info("=== AUTON Orchestration Run %s%s ===", self.state.run_id,
                    f" (resumed, session {self.state.resume_count + 1})" if resume else "")
        logger.info("Goal: %s", goal)
        self._init_agents()

        self._pause_requested = False
        self._main_task = asyncio.current_task()
        restore_signals = self._install_pause_handlers()
        try:
            return await self._run_phases(goal, state_path, resume)
        except asyncio.CancelledError:
            if not self._pause_requested:
                raise
            if self._main_task is not None and hasattr(self._main_task, "uncancel"):
                self._main_task.uncancel()
            return self._pause(state_path)
        finally:
            restore_signals()

    async def _run_phases(self, goal: str, state_path: Path, resume: bool) -> dict[str, Any]:
        run_id = self.state.run_id
        manager: ManagerAgent = self._agents["manager"]
        try:
            if resume:
                tasks = self._restore_graph()
            else:
                planned = await self._plan(goal, state_path)
                if isinstance(planned, dict):
                    return planned
                tasks = planned

            # A resume skips design unless the pause landed inside it.
            if not self.state.design_adopted:
                await self._design(tasks, state_path)

            # Phase 3: Development loop
            self.state.phase = "developing"
            self.state.save(state_path)
            logger.info("--- Phase 3: Development ---")

            # Configurable so a local run can be capped tightly: a local model
            # that cannot tool-call reliably will otherwise spend fifty
            # iterations discovering that. [orchestrator].max_iterations
            max_iterations = int(
                self.config.get("orchestrator", {}).get("max_iterations", 50)
            )
            # A resumed session numbers its iterations after the last one.
            first = self.state.iteration if resume else 0
            for iteration in range(first, first + max_iterations):
                if self._pause_requested:
                    # The cancellation normally lands first; this catches one
                    # that something below swallowed.
                    raise asyncio.CancelledError
                self.state.iteration = iteration
                self.state.total_cost_usd = self.cost_tracker.total_cost_usd
                self._checkpoint(state_path)

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
                            logger.error("Agent %s failed: %s", slot.agent.agent_id, result,
                                         exc_info=result)
                            self.task_graph.fail(task_node.task_id, f"agent error: {result}")
                            self.state.tasks_failed += 1
                        else:
                            await self._handle_result(task_node, result)

                # Check for approved tasks to merge
                self._merge_approved()

                # Small delay to avoid tight loops
                await asyncio.sleep(1)

            # Phase 4: Final integration check
            self.state.phase = "integrating"
            self._checkpoint(state_path)
            logger.info("--- Phase 4: Final Integration ---")

            integrator = self._agents["integrator"]
            final_check = await integrator.full_integration_check()

            # Independent verification: build the kernel and boot it in QEMU.
            # This is the engine's own gate, separate from agent self-report.
            build_result = await self.build_validator.build(timeout=self.build_timeout)
            test_result = None
            composition_result = None
            if build_result.success:
                test_result = await self.test_validator.run_tests()
                if self.composition_checks:
                    composition_result = await self.composition_validator.validate(
                        subsystems=sorted(
                            {t.get("subsystem", "") for t in tasks if t.get("subsystem")}
                        )
                    )
            else:
                logger.warning(
                    "Final build failed with %d errors", len(build_result.errors)
                )

            validation_ok = build_result.success and bool(
                test_result and test_result.success
            )
            if composition_result is not None:
                validation_ok = validation_ok and composition_result.success

            self.state.phase = "done"
            self._checkpoint(state_path)

            success = (self.task_graph.is_complete
                       and final_check.get("success", False) and validation_ok)
            return {
                "success": success,
                "error": None if success else self._failure_summary(
                    final_check, build_result, test_result, composition_result),
                "run_id": run_id,
                "progress": self.task_graph.progress,
                "total_cost_usd": self.cost_tracker.total_cost_usd,
                "iterations": self.state.iteration,
                "final_check": final_check,
                "build_ok": build_result.success,
                "test_ok": bool(test_result and test_result.success),
                "composition_ok": (
                    composition_result.success
                    if composition_result is not None
                    else None
                ),
            }

        except Exception as e:
            logger.exception("Orchestration failed: %s", e)
            self.state.phase = "error"
            self.state.save(state_path)
            return {"success": False, "error": str(e), "cost": self.cost_tracker.total_cost_usd}

    # ------------------------------------------------------------------ #
    # Planning and design (phases 1 and 2)
    # ------------------------------------------------------------------ #

    async def _plan(self, goal: str, state_path: Path) -> list[dict[str, Any]] | dict[str, Any]:
        """Phase 1: the task list, or a result dict saying why there is none."""
        self.state.phase = "planning"
        self.state.save(state_path)
        logger.info("--- Phase 1: Planning ---")

        manager: ManagerAgent = self._agents["manager"]
        seeds = getattr(self, "seed_tasks", [])
        if self.workflow_mode == WorkflowMode.KERNEL_BUILD:
            tasks = await manager.decompose_goal(goal, seed_tasks=seeds)
        elif self.workflow_mode == WorkflowMode.SLM_TRAINING:
            tasks = self.task_graph.create_slm_training_tasks(goal)
        elif self.workflow_mode == WorkflowMode.DUAL:
            kernel_tasks = await manager.decompose_goal(goal)
            slm_tasks = self.task_graph.create_slm_training_tasks(goal)
            tasks = kernel_tasks + slm_tasks
        else:
            return {"success": False, "error": f"Unknown workflow mode: {self.workflow_mode}"}

        self.state.tasks_created = len(tasks)
        if not tasks:
            return {"success": False, "error": "Manager produced no tasks"}

        self.task_graph.add_tasks(tasks)
        logger.info("Task graph: %d tasks, order: %s",
                    len(tasks), self.task_graph.topological_order())
        self._checkpoint(state_path)
        return tasks

    async def _design(self, tasks: list[dict[str, Any]], state_path: Path) -> None:
        """Phase 2: the architect designs each subsystem's interfaces."""
        self.state.phase = "designing"
        self._checkpoint(state_path)
        logger.info("--- Phase 2: Design ---")

        architect: ArchitectAgent = self._agents["architect"]
        # Only subsystems someone will write kernel code for. On the w18 live
        # Analyst run the manager labelled analysis tasks `sys` and `pkg`, and
        # the architect spent the run designing kernel headers nobody needed.
        subsystems = sorted(set(t.get("subsystem", "") for t in tasks
                                if t.get("subsystem")
                                and (t.get("assigned_to") or "developer") in KERNEL_ROLES))
        for subsystem in subsystems:
            design = await architect.design_subsystem(subsystem)
            self.workspace.checkout_main()
            self._adopt_design(design.get("branch"))
        self.state.design_adopted = True
        self._checkpoint(state_path)

    # ------------------------------------------------------------------ #
    # Pause and resume (w17)
    # ------------------------------------------------------------------ #

    def _checkpoint(self, state_path: Path) -> None:
        """Save state with the whole task graph: what a resume starts from."""
        self.state.graph = self.task_graph.to_dict()
        self.state.save(state_path)

    def request_pause(self) -> None:
        """Stop at the next await: commit the work in flight, save, return.

        Installed as the SIGTERM/SIGINT handler, so a time budget ends a
        session instead of the run.
        """
        if self._pause_requested:
            return
        self._pause_requested = True
        logger.warning("Pause requested: committing work in flight and saving the task graph")
        task = getattr(self, "_main_task", None)
        if task is not None and not task.done():
            task.cancel()

    def _install_pause_handlers(self):
        """SIGTERM and SIGINT pause the run. Returns a function that restores
        the previous handlers."""
        sigs = [signal.SIGTERM, signal.SIGINT]
        loop = asyncio.get_running_loop()
        try:
            for sig in sigs:
                loop.add_signal_handler(sig, self.request_pause)
        except (NotImplementedError, RuntimeError, ValueError):
            # Windows has no loop signal handlers; a worker thread has no
            # signals at all. Fall back to the plain handler where possible.
            for sig in sigs:
                try:
                    loop.remove_signal_handler(sig)
                except (NotImplementedError, RuntimeError, ValueError):
                    pass
            previous = {}
            try:
                for sig in sigs:
                    previous[sig] = signal.signal(
                        sig, lambda *_: loop.call_soon_threadsafe(self.request_pause))
            except ValueError:          # not the main thread
                for sig, handler in previous.items():
                    signal.signal(sig, handler)
                return lambda: None

            def restore_plain() -> None:
                for sig, handler in previous.items():
                    signal.signal(sig, handler)
            return restore_plain

        def restore_loop() -> None:
            for sig in sigs:
                loop.remove_signal_handler(sig)
        return restore_loop

    def _pause(self, state_path: Path) -> dict[str, Any]:
        """Commit the work in flight on its branch, save the graph, and report.

        The workspace is one checkout, so the work in flight is whatever sits
        on the checked-out branch. `checkout_main` commits it there before
        leaving, which is the same rule that stopped a checkout orphaning work.
        """
        warning = None
        try:
            current = self.workspace.current_branch()
            message = f"WIP: paused at iteration {self.state.iteration}"
            if current and self.workspace.commit_pending(current, message):
                logger.info("Committed work in flight on %s", current)
            self.workspace.checkout_main()
            self.state.head_at_save = self.workspace.main_head()
        except Exception as exc:          # noqa: BLE001 — the graph must still be saved
            # A stale index.lock, a checkout that conflicts: the work in flight
            # may be uncommitted, but the graph is still worth saving, and the
            # caller must still hear "paused" rather than a traceback.
            warning = f"work in flight may be uncommitted: {exc}"
            logger.error("Pause could not commit the work in flight: %s", exc)
            self.state.head_at_save = ""

        self.state.phase = "paused"
        self._checkpoint(state_path)
        progress = self.task_graph.progress
        logger.warning("Orchestration paused at iteration %d | Progress: %s",
                       self.state.iteration, progress)
        return {
            "success": False,
            "paused": True,
            "error": "paused; resume with --resume",
            "run_id": self.state.run_id,
            "progress": progress,
            "iterations": self.state.iteration,
            "total_cost_usd": self.cost_tracker.total_cost_usd,
            **({"pause_warning": warning} if warning else {}),
        }

    def _resume_refusal(self, state_path: Path, goal: str, model: str) -> str | None:
        """Why this run cannot resume, or None. Each reason names what differs."""
        if not state_path.exists():
            return f"no saved run at {state_path}; start a new run without --resume"
        saved = OrchestratorState.load(state_path)
        if saved.format < STATE_FORMAT:
            return (f"state format {saved.format} predates resume (format {STATE_FORMAT}) "
                    f"and saved no task graph; start a new run")
        if saved.goal != goal:
            return (f"saved goal {saved.goal!r} differs from {goal!r}; resume with the "
                    f"saved goal, or start a new run")
        if saved.model and saved.model != model:
            return (f"saved run used model {saved.model!r} and the config says {model!r}; "
                    f"a model change is a different experiment — pre-register it and "
                    f"start a new run")
        if not saved.graph:
            return ("no task graph was saved: the run stopped before planning finished; "
                    "start a new run")
        if saved.phase == "done":
            return f"run {saved.run_id} already finished"
        head = self.workspace.main_head()
        if saved.head_at_save and saved.head_at_save != head:
            return (f"main moved since the pause (was {saved.head_at_save[:8]}, now "
                    f"{head[:8]}); the saved graph never saw that work")
        return None

    def _restore_graph(self) -> list[dict[str, Any]]:
        """Load the saved graph; work that was in flight goes back to READY.

        A task that was RUNNING or waiting for review when the session ended
        is handed to an agent again, told that its branch already holds what
        was done, so it continues rather than starting over.
        """
        self.task_graph.load_nodes(self.state.graph)
        for node in self.task_graph.all_tasks:
            if node.state in (TaskState.RUNNING, TaskState.REVIEW):
                node.state = TaskState.READY
                node.assigned_agent_id = None
                node.data["resumed"] = True
        logger.info("Resumed run %s at iteration %d: %s", self.state.run_id,
                    self.state.iteration, self.task_graph.progress)
        return [n.data for n in self.task_graph.all_tasks]

    async def _execute_agent_task(self, agent: Any, task_node: Any) -> TaskResult:
        """Execute a task with the appropriate agent method."""
        self.workspace.checkout_main()  # Start from a clean state

        if hasattr(agent, "implement_task"):
            return await agent.implement_task(task_node.data)
        else:
            return await agent.execute_task(task_node.data)

    def _failure_summary(self, final_check, build_result, test_result,
                         composition_result) -> str:
        """Why a run did not succeed, in one line. Both w11 runs printed
        `Orchestration failed: unknown`, which told nobody anything."""
        reasons = []
        for node in self.task_graph.all_tasks:
            if node.state is TaskState.FAILED:
                why = node.data.get("failure_reason", "no reason")
                reasons.append(f"{node.task_id} failed ({why})")
            elif node.state is not TaskState.MERGED:
                reasons.append(f"{node.task_id} ended {node.state.value}")
        if not final_check.get("success", False):
            reasons.append("integration check failed")
        if not build_result.success:
            reasons.append(f"build failed ({len(build_result.errors)} errors)")
        elif not (test_result and test_result.success):
            reasons.append("boot/tests failed")
        if composition_result is not None and not composition_result.success:
            reasons.append("composition check failed")
        return "; ".join(reasons) or "no task reached a terminal state"

    async def _handle_result(self, task_node: Any, result: Any) -> None:
        """Route one finished task: merge, review, or fail, and always say why.

        The w11 runs (F6, V8) ended with `Orchestration failed: unknown` after
        a task that wrote nothing was sent to review as branch `main`, a local
        model invented code to reject, and the rejection blocked the chain for
        good. Each branch below exists for one of those.
        """
        task_id = task_node.task_id
        task_node.data.pop("resumed", None)
        if not (isinstance(result, TaskResult) and result.success):
            summary = getattr(result, "summary", "") or "no summary"
            logger.info("Task %s did not succeed: %s", task_id, summary)
            self.task_graph.fail(task_id, f"agent reported failure: {summary}")
            self.state.tasks_failed += 1
            return

        if not result.branch:
            # No branch: the agent was not asked to produce a change (a design
            # or read task). There is nothing to review, and reviewing nothing
            # is what made the model hallucinate a diff.
            logger.info("Task %s produced no branch; merged without review", task_id)
            self.task_graph.update_state(task_id, TaskState.MERGED)
            return

        if self.workspace.commit_pending(
                result.branch, f"{task_id}: uncommitted agent output"):
            logger.info("Committed uncommitted work on %s for %s", result.branch, task_id)

        if not self.workspace.has_changes(result.branch):
            logger.info("Task %s: branch %s has no changes against main",
                        task_id, result.branch)
            self.task_graph.fail(
                task_id, f"no output: branch {result.branch} is identical to main")
            self.state.tasks_failed += 1
            return

        task_node.data["branch"] = result.branch
        self.task_graph.update_state(task_id, TaskState.REVIEW)
        await self._trigger_review(task_node, result)

    def _merge_approved(self) -> None:
        """Merge every approved branch into main, and mark the graph.

        Merging is mechanical, so the engine does it with git rather than asking
        a model to. Before w12 an LLM integrator "merged" and updated on-disk
        metadata only; the graph node stayed APPROVED, so no dependent of an
        approved task ever became ready.
        """
        for node in self.task_graph.get_tasks_by_state(TaskState.APPROVED):
            branch = node.data.get("branch")
            if branch and self.workspace.merge_branch(branch):
                self.task_graph.update_state(node.task_id, TaskState.MERGED)
                self.state.tasks_completed += 1
                continue
            # A conflict with main is feedback like any other: the author
            # rebuilds against the new main, within the same round limit.
            limit = int(self.config.get("orchestrator", {}).get("max_review_rounds", 3))
            requeued = self.task_graph.requeue(node.task_id, {
                "verdict": "request_changes",
                "summary": f"branch {branch} does not merge cleanly into main; "
                           f"rebuild your change against the current main"})
            if requeued.review_rounds >= limit:
                self.task_graph.fail(node.task_id, f"merge conflict with main ({branch})")
                self.state.tasks_failed += 1

    def _adopt_design(self, branch: str | None) -> bool:
        """Merge a design branch into main, so developers build on its headers.

        Before w13 the architect's headers stayed on their arch-* branch: the
        developers, branching from main, never saw the interfaces they were
        told to implement. A design that does not compile is not adopted.
        """
        if not branch:
            return False
        # checkout_main has already committed the architect's pending work.
        if not self.workspace.has_changes(branch):
            return False
        errors = self._syntax_errors(branch)
        if errors is not None:
            logger.warning("Design %s not adopted, it does not compile:\n%s", branch, errors)
            return False
        return self.workspace.merge_branch(branch)

    def _stage_subject(self, resume: bool) -> str | None:
        """Stage the subject (or, on resume, check the one already staged).
        Returns why it could not be, or None."""
        try:
            if resume and self.workspace.subject_path.exists():
                self.workspace.verify_subject(self.state.subject_hash)
                self.subject_hash = self.state.subject_hash
            else:
                self.subject_hash = self.workspace.stage_subject(self.subject_path)
        except WorkspaceError as exc:
            return f"subject: {exc}"
        self.state.subject_hash = self.subject_hash
        return None

    def _syntax_errors(self, branch: str) -> str | None:
        """The compiler's errors for the C files `branch` changed, or None.

        With a staged subject, the subject is re-hashed first: a record built
        on evidence that changed is refused whatever it says (A2 layer 3).
        """
        subject = getattr(self, "subject_hash", "")
        if subject:
            try:
                self.workspace.verify_subject(subject)
            except WorkspaceError as exc:
                return str(exc)
        _, changed = self.workspace.branch_diff(branch)
        self.workspace.checkout(branch)
        try:
            return syntax_gate.check(self.workspace.path, changed)
        finally:
            self.workspace.checkout_main()

    async def _trigger_review(self, task_node: Any, result: TaskResult) -> None:
        """Review a task with real changes; a rejection returns to its author."""
        if not result.branch:
            return

        # Whether C compiles is not a judgement call: a compiler answers it
        # before a reviewer model is asked anything (syntax_gate.py).
        errors = self._syntax_errors(result.branch)
        if errors is not None:
            review_result = {"verdict": "request_changes",
                             "summary": f"the change does not compile:\n{errors}"}
        else:
            reviewer_slot = self.scheduler.get_available_agent("reviewer")
            if reviewer_slot is None:
                logger.info("No reviewer available, task %s queued for review",
                            task_node.task_id)
                return

            reviewer_slot.busy = True
            brief = f"{task_node.title}\n{task_node.data.get('description', '')}".strip()
            review_result = await reviewer_slot.agent.review_branch(
                task_node.task_id, result.branch, brief
            )
            reviewer_slot.busy = False

            if review_result.get("verdict") == "approve":
                self.task_graph.update_state(task_node.task_id, TaskState.APPROVED)
                return

        limit = int(self.config.get("orchestrator", {}).get("max_review_rounds", 3))
        node = self.task_graph.requeue(task_node.task_id, review_result)
        summary = review_result.get("summary", "no summary")
        logger.info("Review round %d/%d for %s: %s",
                    node.review_rounds, limit, task_node.task_id, summary)
        if node.review_rounds >= limit:
            self.task_graph.fail(
                task_node.task_id,
                f"rejected {node.review_rounds} time(s); last review: {summary}")
            self.state.tasks_failed += 1

