"""Integration tests for dual workflow mode.

Tests that OrchestrationEngine in 'dual' mode creates both kernel and SLM
agents, has correct cost tracking, and that mixed task graphs (kernel + SLM)
work properly together.
"""

import pytest
from pathlib import Path
from unittest.mock import patch

from orchestrator.core.engine import OrchestrationEngine, WorkflowMode
from orchestrator.core.task_graph import TaskGraph, TaskState


@pytest.fixture
def dual_config():
    return {
        "llm": {
            "model": "ollama/test-model",
            "max_tokens": 4096,
            "api_keys": {},
            "cost": {"max_cost_usd": 50.0, "warn_at_usd": 25.0},
        },
        "kernel": {"arch": "x86_64"},
        "workspace": {"branch_prefix": "agent"},
        "agents": {
            "developer_count": 2,
            "reviewer_count": 1,
            "tester_count": 1,
            "data_scientist_count": 1,
            "model_architect_count": 1,
            "training_agent_count": 2,
        },
        "workflow": {"mode": "dual"},
    }


@pytest.fixture
def dual_engine(dual_config, tmp_path):
    """Create an OrchestrationEngine in dual mode."""
    spec_path = tmp_path / "kernel_spec"
    spec_path.mkdir()
    with patch("orchestrator.core.engine.GitWorkspace"):
        engine = OrchestrationEngine(
            workspace_path=tmp_path,
            kernel_spec_path=spec_path,
            config=dual_config,
        )
    return engine


def test_dual_mode_workflow(dual_engine):
    """Engine correctly identifies dual workflow mode."""
    assert dual_engine.workflow_mode == WorkflowMode.DUAL


def test_dual_mode_creates_all_agents(dual_engine):
    """Dual mode creates both kernel and SLM agents."""
    dual_engine._init_agents()

    # Kernel agents
    assert "manager" in dual_engine._agents
    assert "architect" in dual_engine._agents
    assert "integrator" in dual_engine._agents
    assert "dev-01" in dual_engine._agents
    assert "dev-02" in dual_engine._agents
    assert "reviewer-01" in dual_engine._agents
    assert "tester-01" in dual_engine._agents

    # SLM agents
    assert "data_scientist" in dual_engine._agents
    assert "model_architect" in dual_engine._agents
    assert "training-01" in dual_engine._agents
    assert "training-02" in dual_engine._agents


def test_dual_mode_cost_tracking(dual_engine):
    """Dual mode respects the higher cost budget."""
    assert dual_engine.cost_tracker.max_cost_usd == 50.0
    assert dual_engine.cost_tracker.warn_at_usd == 25.0


def test_dual_mode_total_agent_count(dual_engine):
    """Dual mode should have the combined agent count."""
    dual_engine._init_agents()

    # manager(1) + architect(1) + integrator(1) + devs(2) + reviewer(1) + tester(1)
    # + data_scientist(1) + model_architect(1) + training(2) = 11
    assert len(dual_engine._agents) == 11


def test_dual_mode_mixed_task_graph():
    """A mixed task graph with both kernel and SLM tasks works correctly."""
    graph = TaskGraph()

    # Kernel tasks
    kernel_tasks = [
        {"task_id": "boot-001", "title": "Boot loader", "subsystem": "boot",
         "dependencies": [], "assigned_to": "developer"},
        {"task_id": "mm-001", "title": "Memory manager", "subsystem": "mm",
         "dependencies": ["boot-001"], "assigned_to": "developer"},
    ]

    # SLM tasks
    slm_tasks = graph.create_slm_training_tasks("Train SLM for kernel")

    all_tasks = kernel_tasks + slm_tasks
    graph.add_tasks(all_tasks)

    # Should have both kernel and SLM tasks
    order = graph.topological_order()
    assert "boot-001" in order
    assert "mm-001" in order
    assert "slm-data-prep" in order
    assert "slm-training" in order


def test_dual_mode_independent_task_streams():
    """Kernel and SLM tasks should be schedulable independently."""
    graph = TaskGraph()

    kernel_tasks = [
        {"task_id": "boot-001", "title": "Boot loader", "subsystem": "boot",
         "dependencies": [], "assigned_to": "developer"},
    ]
    slm_tasks = graph.create_slm_training_tasks("Train SLM")

    graph.add_tasks(kernel_tasks + slm_tasks)

    # Both boot-001 and slm-data-prep/slm-arch-design should be ready
    ready = graph.get_ready_tasks()
    ready_ids = {t.task_id for t in ready}
    assert "boot-001" in ready_ids
    assert "slm-data-prep" in ready_ids
    assert "slm-arch-design" in ready_ids


def test_dual_mode_partial_completion():
    """Completing kernel tasks does not affect SLM task readiness and vice versa."""
    graph = TaskGraph()

    kernel_tasks = [
        {"task_id": "boot-001", "title": "Boot", "subsystem": "boot",
         "dependencies": [], "assigned_to": "developer"},
        {"task_id": "mm-001", "title": "MM", "subsystem": "mm",
         "dependencies": ["boot-001"], "assigned_to": "developer"},
    ]
    slm_tasks = graph.create_slm_training_tasks("Train SLM")
    graph.add_tasks(kernel_tasks + slm_tasks)

    # Complete kernel boot task
    graph.update_state("boot-001", TaskState.MERGED)

    # mm-001 should now be ready
    ready_ids = {t.task_id for t in graph.get_ready_tasks()}
    assert "mm-001" in ready_ids

    # SLM tasks unaffected -- data-prep and arch-design still ready
    assert "slm-data-prep" in ready_ids
    assert "slm-arch-design" in ready_ids


def test_dual_mode_progress_covers_all_tasks():
    """progress dict includes counts from both kernel and SLM tasks."""
    graph = TaskGraph()

    kernel_tasks = [
        {"task_id": "boot-001", "title": "Boot", "subsystem": "boot",
         "dependencies": [], "assigned_to": "developer"},
    ]
    slm_tasks = graph.create_slm_training_tasks("Train SLM")
    graph.add_tasks(kernel_tasks + slm_tasks)

    # 1 kernel + 7 SLM tasks = 8 total
    total_count = sum(graph.progress.values())
    assert total_count == 8


def test_dual_mode_is_complete_requires_all():
    """is_complete is True only when ALL tasks (kernel + SLM) are terminal."""
    graph = TaskGraph()

    kernel_tasks = [
        {"task_id": "boot-001", "title": "Boot", "subsystem": "boot",
         "dependencies": [], "assigned_to": "developer"},
    ]
    slm_tasks = graph.create_slm_training_tasks("Train SLM")
    graph.add_tasks(kernel_tasks + slm_tasks)

    # Complete only kernel task -- not complete
    graph.update_state("boot-001", TaskState.MERGED)
    assert not graph.is_complete

    # Complete all SLM tasks too
    for task in slm_tasks:
        graph.update_state(task["task_id"], TaskState.MERGED)

    assert graph.is_complete


def test_dual_mode_different_architectures(tmp_path):
    """Dual mode works with different target architectures."""
    for arch in ["x86_64", "aarch64", "riscv64"]:
        config = {
            "llm": {
                "model": "ollama/test-model",
                "max_tokens": 4096,
                "api_keys": {},
                "cost": {"max_cost_usd": 50.0, "warn_at_usd": 25.0},
            },
            "kernel": {"arch": arch},
            "workspace": {"branch_prefix": "agent"},
            "agents": {
                "developer_count": 1,
                "reviewer_count": 1,
                "tester_count": 1,
                "training_agent_count": 1,
            },
            "workflow": {"mode": "dual"},
        }

        spec_path = tmp_path / f"kernel_spec_{arch}"
        spec_path.mkdir()
        with patch("orchestrator.core.engine.GitWorkspace"):
            engine = OrchestrationEngine(
                workspace_path=tmp_path,
                kernel_spec_path=spec_path,
                config=config,
            )
        assert engine.arch_profile.name == arch
        assert engine.workflow_mode == WorkflowMode.DUAL


def test_dual_mode_scheduler_registers_all_roles(dual_engine):
    """The scheduler should have pools for both kernel and SLM agent roles."""
    dual_engine._init_agents()

    scheduler_status = dual_engine.scheduler.status()
    assert scheduler_status["developer"]["total"] == 2
    assert scheduler_status["reviewer"]["total"] == 1
    assert scheduler_status["tester"]["total"] == 1
    assert scheduler_status["integrator"]["total"] == 1
    assert scheduler_status["data_scientist"]["total"] == 1
    assert scheduler_status["model_architect"]["total"] == 1
    assert scheduler_status["training"]["total"] == 2
