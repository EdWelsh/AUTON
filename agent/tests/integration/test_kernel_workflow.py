"""Integration tests for kernel build workflow.

Tests that OrchestrationEngine correctly initializes in kernel_build mode,
creates the right agents, and that TaskGraph properly manages kernel build
tasks with dependencies.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.core.engine import OrchestrationEngine, WorkflowMode
from orchestrator.core.task_graph import TaskGraph, TaskNode, TaskState
from orchestrator.agents.base_agent import AgentRole


@pytest.fixture
def kernel_config():
    return {
        "llm": {
            "model": "ollama/test-model",
            "max_tokens": 4096,
            "api_keys": {},
            "cost": {"max_cost_usd": 10.0, "warn_at_usd": 5.0},
        },
        "kernel": {"arch": "x86_64"},
        "workspace": {"branch_prefix": "agent"},
        "agents": {"developer_count": 1, "reviewer_count": 1, "tester_count": 1},
        "workflow": {"mode": "kernel_build"},
    }


@pytest.fixture
def kernel_engine(kernel_config, tmp_path):
    """Create an OrchestrationEngine in kernel_build mode with GitWorkspace mocked."""
    spec_path = tmp_path / "kernel_spec"
    spec_path.mkdir()
    with patch("orchestrator.core.engine.GitWorkspace"):
        engine = OrchestrationEngine(
            workspace_path=tmp_path,
            kernel_spec_path=spec_path,
            config=kernel_config,
        )
    return engine


def test_engine_creates_kernel_agents(kernel_engine):
    """Engine in kernel_build mode sets the correct workflow mode."""
    assert kernel_engine.workflow_mode == WorkflowMode.KERNEL_BUILD


def test_engine_workflow_mode_from_config(kernel_config, tmp_path):
    """WorkflowMode is parsed from the config dict."""
    spec_path = tmp_path / "kernel_spec"
    spec_path.mkdir()
    with patch("orchestrator.core.engine.GitWorkspace"):
        engine = OrchestrationEngine(
            workspace_path=tmp_path,
            kernel_spec_path=spec_path,
            config=kernel_config,
        )
    assert engine.workflow_mode == WorkflowMode.KERNEL_BUILD


def test_engine_arch_profile_loaded(kernel_engine):
    """Engine loads the architecture profile from config."""
    assert kernel_engine.arch_profile.name == "x86_64"
    assert kernel_engine.arch_profile.display_name == "x86_64 (AMD64)"


def test_engine_cost_tracker_initialized(kernel_engine):
    """CostTracker is initialized from llm.cost config."""
    assert kernel_engine.cost_tracker.max_cost_usd == 10.0
    assert kernel_engine.cost_tracker.warn_at_usd == 5.0


def test_engine_init_kernel_agents(kernel_engine):
    """_init_agents creates manager, architect, devs, reviewers, testers, integrator."""
    kernel_engine._init_agents()

    assert "manager" in kernel_engine._agents
    assert "architect" in kernel_engine._agents
    assert "integrator" in kernel_engine._agents
    assert "dev-01" in kernel_engine._agents
    assert "reviewer-01" in kernel_engine._agents
    assert "tester-01" in kernel_engine._agents


def test_engine_kernel_mode_no_slm_agents(kernel_engine):
    """kernel_build mode should NOT create SLM agents."""
    kernel_engine._init_agents()

    assert "data_scientist" not in kernel_engine._agents
    assert "model_architect" not in kernel_engine._agents
    assert "training-01" not in kernel_engine._agents


def test_engine_agent_count_matches_config(kernel_config, tmp_path):
    """Developer/reviewer/tester counts come from config."""
    spec_path = tmp_path / "kernel_spec"
    spec_path.mkdir()
    kernel_config["agents"]["developer_count"] = 3
    kernel_config["agents"]["reviewer_count"] = 2
    kernel_config["agents"]["tester_count"] = 2

    with patch("orchestrator.core.engine.GitWorkspace"):
        engine = OrchestrationEngine(
            workspace_path=tmp_path,
            kernel_spec_path=spec_path,
            config=kernel_config,
        )
    engine._init_agents()

    dev_agents = [k for k in engine._agents if k.startswith("dev-")]
    reviewer_agents = [k for k in engine._agents if k.startswith("reviewer-")]
    tester_agents = [k for k in engine._agents if k.startswith("tester-")]

    assert len(dev_agents) == 3
    assert len(reviewer_agents) == 2
    assert len(tester_agents) == 2


def test_task_graph_kernel_tasks():
    """TaskGraph can track kernel build tasks with dependencies."""
    graph = TaskGraph()
    tasks = [
        {
            "task_id": "boot-001",
            "title": "Boot loader",
            "subsystem": "boot",
            "dependencies": [],
            "assigned_to": "developer",
        },
        {
            "task_id": "mm-001",
            "title": "Memory manager",
            "subsystem": "mm",
            "dependencies": ["boot-001"],
            "assigned_to": "developer",
        },
    ]
    graph.add_tasks(tasks)
    assert len(graph.topological_order()) == 2

    ready = graph.get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].task_id == "boot-001"


def test_task_graph_dependency_ordering():
    """Topological order respects dependencies."""
    graph = TaskGraph()
    tasks = [
        {"task_id": "a", "title": "A", "subsystem": "boot", "dependencies": [], "assigned_to": "developer"},
        {"task_id": "b", "title": "B", "subsystem": "mm", "dependencies": ["a"], "assigned_to": "developer"},
        {"task_id": "c", "title": "C", "subsystem": "sched", "dependencies": ["b"], "assigned_to": "developer"},
    ]
    graph.add_tasks(tasks)
    order = graph.topological_order()
    assert order.index("a") < order.index("b")
    assert order.index("b") < order.index("c")


def test_task_graph_parallel_tasks():
    """Tasks without dependencies on each other are both ready."""
    graph = TaskGraph()
    tasks = [
        {"task_id": "boot-001", "title": "Boot", "subsystem": "boot", "dependencies": [], "assigned_to": "developer"},
        {"task_id": "serial-001", "title": "Serial", "subsystem": "drivers", "dependencies": [], "assigned_to": "developer"},
    ]
    graph.add_tasks(tasks)
    ready = graph.get_ready_tasks()
    assert len(ready) == 2
    ready_ids = {t.task_id for t in ready}
    assert ready_ids == {"boot-001", "serial-001"}


def test_task_graph_cascade_readiness():
    """Completing a dependency makes dependent tasks ready."""
    graph = TaskGraph()
    tasks = [
        {"task_id": "boot-001", "title": "Boot", "subsystem": "boot", "dependencies": [], "assigned_to": "developer"},
        {"task_id": "mm-001", "title": "MM", "subsystem": "mm", "dependencies": ["boot-001"], "assigned_to": "developer"},
    ]
    graph.add_tasks(tasks)

    # Only boot-001 is ready initially
    assert len(graph.get_ready_tasks()) == 1
    assert graph.get_ready_tasks()[0].task_id == "boot-001"

    # Mark boot-001 as merged (terminal success state)
    graph.update_state("boot-001", TaskState.RUNNING)
    graph.update_state("boot-001", TaskState.MERGED)

    # Now mm-001 should be ready
    ready = graph.get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].task_id == "mm-001"


def test_task_graph_is_complete():
    """is_complete returns True when all tasks are in terminal states."""
    graph = TaskGraph()
    tasks = [
        {"task_id": "boot-001", "title": "Boot", "subsystem": "boot", "dependencies": [], "assigned_to": "developer"},
        {"task_id": "mm-001", "title": "MM", "subsystem": "mm", "dependencies": [], "assigned_to": "developer"},
    ]
    graph.add_tasks(tasks)
    assert not graph.is_complete

    graph.update_state("boot-001", TaskState.MERGED)
    assert not graph.is_complete

    graph.update_state("mm-001", TaskState.MERGED)
    assert graph.is_complete


def test_task_graph_progress():
    """progress returns counts by state."""
    graph = TaskGraph()
    tasks = [
        {"task_id": "a", "title": "A", "subsystem": "x", "dependencies": [], "assigned_to": "developer"},
        {"task_id": "b", "title": "B", "subsystem": "x", "dependencies": [], "assigned_to": "developer"},
        {"task_id": "c", "title": "C", "subsystem": "x", "dependencies": ["a"], "assigned_to": "developer"},
    ]
    graph.add_tasks(tasks)

    # a and b are ready, c is pending
    progress = graph.progress
    assert progress.get("ready", 0) == 2
    assert progress.get("pending", 0) == 1


def test_task_graph_cycle_detection():
    """Cycle in dependencies raises ValueError."""
    graph = TaskGraph()
    tasks = [
        {"task_id": "a", "title": "A", "subsystem": "x", "dependencies": ["b"], "assigned_to": "developer"},
        {"task_id": "b", "title": "B", "subsystem": "x", "dependencies": ["a"], "assigned_to": "developer"},
    ]
    graph.add_tasks(tasks)
    with pytest.raises(ValueError, match="Cycle detected"):
        graph.topological_order()


def test_task_graph_assign_agent():
    """assign_agent records the agent and sets state to RUNNING."""
    graph = TaskGraph()
    graph.add_task({"task_id": "boot-001", "title": "Boot", "subsystem": "boot", "dependencies": [], "assigned_to": "developer"})
    graph.assign_agent("boot-001", "dev-01")
    node = graph.get_task("boot-001")
    assert node.state == TaskState.RUNNING
    assert node.assigned_agent_id == "dev-01"


def test_task_graph_failed_dependency_blocks_dependent():
    """A failed dependency does not unblock dependent tasks."""
    graph = TaskGraph()
    tasks = [
        {"task_id": "a", "title": "A", "subsystem": "x", "dependencies": [], "assigned_to": "developer"},
        {"task_id": "b", "title": "B", "subsystem": "x", "dependencies": ["a"], "assigned_to": "developer"},
    ]
    graph.add_tasks(tasks)

    graph.update_state("a", TaskState.FAILED)

    # b should still be pending since "a" was not MERGED
    ready = graph.get_ready_tasks()
    assert len(ready) == 0


def test_engine_has_task_graph_and_scheduler(kernel_engine):
    """Engine has a task graph and scheduler properly wired together."""
    assert kernel_engine.task_graph is not None
    assert kernel_engine.scheduler is not None
    assert kernel_engine.scheduler.graph is kernel_engine.task_graph
