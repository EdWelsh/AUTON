"""Integration tests for SLM training workflow.

Tests that OrchestrationEngine correctly initializes in slm_training mode,
that TaskGraph.create_slm_training_tasks() produces a valid task pipeline,
and that SLM-specific agents are created.
"""

import pytest
from pathlib import Path
from unittest.mock import patch

from orchestrator.core.engine import OrchestrationEngine, WorkflowMode
from orchestrator.core.task_graph import TaskGraph, TaskState


@pytest.fixture
def slm_config():
    return {
        "llm": {
            "model": "ollama/test-model",
            "max_tokens": 4096,
            "api_keys": {},
            "cost": {"max_cost_usd": 10.0, "warn_at_usd": 5.0},
        },
        "kernel": {"arch": "x86_64"},
        "workspace": {"branch_prefix": "agent"},
        "agents": {
            "developer_count": 1,
            "reviewer_count": 1,
            "tester_count": 1,
            "data_scientist_count": 1,
            "model_architect_count": 1,
            "training_agent_count": 1,
        },
        "workflow": {"mode": "slm_training"},
        "slm": {
            "models_path": "../SLM/models",
            "datasets_path": "../SLM/datasets",
        },
    }


@pytest.fixture
def slm_engine(slm_config, tmp_path):
    """Create an OrchestrationEngine in slm_training mode."""
    spec_path = tmp_path / "kernel_spec"
    spec_path.mkdir()
    with patch("orchestrator.core.engine.GitWorkspace"):
        engine = OrchestrationEngine(
            workspace_path=tmp_path,
            kernel_spec_path=spec_path,
            config=slm_config,
        )
    return engine


def test_engine_slm_mode(slm_engine):
    """Engine correctly identifies slm_training workflow mode."""
    assert slm_engine.workflow_mode == WorkflowMode.SLM_TRAINING


def test_engine_slm_agents_created(slm_engine):
    """slm_training mode creates SLM-specific agents."""
    slm_engine._init_agents()

    assert "data_scientist" in slm_engine._agents
    assert "model_architect" in slm_engine._agents
    assert "training-01" in slm_engine._agents


def test_engine_slm_mode_also_creates_kernel_agents(slm_engine):
    """SLM mode still creates the core kernel agents (manager, architect, etc.)."""
    slm_engine._init_agents()

    assert "manager" in slm_engine._agents
    assert "architect" in slm_engine._agents
    assert "integrator" in slm_engine._agents


def test_task_graph_creates_slm_tasks():
    """create_slm_training_tasks produces a non-empty task list with data tasks."""
    graph = TaskGraph()
    tasks = graph.create_slm_training_tasks("Train a 150M SLM")
    assert len(tasks) > 0

    task_ids = [t["task_id"] for t in tasks]
    # Should have data prep, architecture, training tasks
    assert any("data" in tid for tid in task_ids)
    assert any("arch" in tid for tid in task_ids)
    assert any("training" in tid for tid in task_ids)


def test_slm_task_ids_are_unique():
    """All SLM task IDs must be unique."""
    graph = TaskGraph()
    tasks = graph.create_slm_training_tasks("Train SLM")
    task_ids = [t["task_id"] for t in tasks]
    assert len(task_ids) == len(set(task_ids))


def test_slm_task_dependencies():
    """SLM tasks form a valid DAG that can be topologically sorted."""
    graph = TaskGraph()
    tasks = graph.create_slm_training_tasks("Train SLM")
    graph.add_tasks(tasks)
    order = graph.topological_order()
    assert len(order) == len(tasks)


def test_slm_task_dependency_chain():
    """SLM tasks have correct dependency ordering: data/arch -> training -> eval -> quant -> export -> integrate."""
    graph = TaskGraph()
    tasks = graph.create_slm_training_tasks("Train SLM")
    graph.add_tasks(tasks)
    order = graph.topological_order()

    # Data prep and arch design should come before training
    assert order.index("slm-data-prep") < order.index("slm-training")
    assert order.index("slm-arch-design") < order.index("slm-training")

    # Training before evaluation
    assert order.index("slm-training") < order.index("slm-evaluation")

    # Evaluation before quantization
    assert order.index("slm-evaluation") < order.index("slm-quantization")

    # Quantization before export
    assert order.index("slm-quantization") < order.index("slm-export")

    # Export before integration
    assert order.index("slm-export") < order.index("slm-integration")


def test_slm_initial_ready_tasks():
    """Only data prep and arch design should be ready initially (no dependencies)."""
    graph = TaskGraph()
    tasks = graph.create_slm_training_tasks("Train SLM")
    graph.add_tasks(tasks)

    ready = graph.get_ready_tasks()
    ready_ids = {t.task_id for t in ready}
    assert ready_ids == {"slm-data-prep", "slm-arch-design"}


def test_slm_training_unblocked_after_prereqs():
    """Training becomes ready once both data prep and arch design are merged."""
    graph = TaskGraph()
    tasks = graph.create_slm_training_tasks("Train SLM")
    graph.add_tasks(tasks)

    # Complete data prep only -- training should still be blocked
    graph.update_state("slm-data-prep", TaskState.MERGED)
    ready_ids = {t.task_id for t in graph.get_ready_tasks()}
    assert "slm-training" not in ready_ids

    # Now complete arch design
    graph.update_state("slm-arch-design", TaskState.MERGED)
    ready_ids = {t.task_id for t in graph.get_ready_tasks()}
    assert "slm-training" in ready_ids


def test_slm_full_pipeline_completion():
    """Completing all SLM tasks in order results in is_complete == True."""
    graph = TaskGraph()
    tasks = graph.create_slm_training_tasks("Train SLM")
    graph.add_tasks(tasks)

    pipeline = [
        "slm-data-prep",
        "slm-arch-design",
        "slm-training",
        "slm-evaluation",
        "slm-quantization",
        "slm-export",
        "slm-integration",
    ]
    for task_id in pipeline:
        graph.update_state(task_id, TaskState.MERGED)

    assert graph.is_complete


def test_slm_tasks_assigned_to_correct_roles():
    """SLM tasks should be assigned to appropriate agent roles."""
    graph = TaskGraph()
    tasks = graph.create_slm_training_tasks("Train SLM")

    role_map = {t["task_id"]: t["assigned_to"] for t in tasks}
    assert role_map["slm-data-prep"] == "data_scientist"
    assert role_map["slm-arch-design"] == "model_architect"
    assert role_map["slm-training"] == "training"
    assert role_map["slm-evaluation"] == "training"
    assert role_map["slm-quantization"] == "training"
    assert role_map["slm-export"] == "training"
    assert role_map["slm-integration"] == "integrator"


def test_slm_tasks_have_priority():
    """SLM tasks should have ascending priority (later tasks have higher number)."""
    graph = TaskGraph()
    tasks = graph.create_slm_training_tasks("Train SLM")

    priorities = {t["task_id"]: t.get("priority", 3) for t in tasks}
    assert priorities["slm-data-prep"] <= priorities["slm-training"]
    assert priorities["slm-training"] <= priorities["slm-evaluation"]
    assert priorities["slm-evaluation"] <= priorities["slm-quantization"]
    assert priorities["slm-quantization"] <= priorities["slm-export"]
    assert priorities["slm-export"] <= priorities["slm-integration"]


def test_slm_tasks_all_in_slm_subsystem():
    """All SLM tasks should belong to the 'slm' subsystem."""
    graph = TaskGraph()
    tasks = graph.create_slm_training_tasks("Train SLM")

    for task in tasks:
        assert task["subsystem"] == "slm", f"Task {task['task_id']} has wrong subsystem"
