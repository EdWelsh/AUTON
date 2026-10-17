"""Tests for orchestration engine."""

from pathlib import Path
import pytest
from orchestrator.core.engine import OrchestrationEngine, WorkflowMode


def test_workflow_mode_enum():
    """Test WorkflowMode enum values."""
    assert WorkflowMode.KERNEL_BUILD.value == "kernel_build"
    assert WorkflowMode.SLM_TRAINING.value == "slm_training"
    assert WorkflowMode.DUAL.value == "dual"


def test_workflow_mode_from_string():
    """Test WorkflowMode creation from string."""
    mode = WorkflowMode("kernel_build")
    assert mode == WorkflowMode.KERNEL_BUILD


def test_a_no_kernel_run_whose_tasks_all_failed_is_not_a_success(tmp_path):
    """w26 review: terminal includes FAILED, so is_complete alone called it a success."""
    from orchestrator.core.engine import OrchestrationEngine
    from orchestrator.core.task_graph import TaskState
    eng = OrchestrationEngine(workspace_path=tmp_path / "ws",
                              kernel_spec_path=Path(__file__).resolve().parents[3] / "kernel_spec",
                              config={"llm": {"model": "anthropic/scripted"},
                                      "workflow": {"mode": "slm_training"}})
    eng.workspace.init()
    from orchestrator.core.state import OrchestratorState
    eng.state = OrchestratorState(run_id="r", goal="g", model="m")
    eng.task_graph.add_tasks([{"task_id": "t-1", "title": "t", "subsystem": "slm",
                               "assigned_to": "training", "dependencies": []}])
    eng.task_graph.update_state("t-1", TaskState.FAILED)
    assert eng._application_result("r")["success"] is False


def test_kernel_tester_tasks_are_not_held_to_produces(tmp_path):
    from orchestrator.core.engine import OrchestrationEngine
    eng = OrchestrationEngine(workspace_path=tmp_path / "ws",
                              kernel_spec_path=Path(__file__).resolve().parents[3] / "kernel_spec",
                              config={"llm": {"model": "anthropic/scripted"}})
    eng.workspace.init()
    eng.task_graph.add_tasks([{"task_id": "t-1", "title": "t", "subsystem": "x",
                               "assigned_to": "tester", "dependencies": [],
                               "produces": ["does/not/exist"]}])
    assert eng._unmet_outputs(eng.task_graph.get_task("t-1"), None) == []
