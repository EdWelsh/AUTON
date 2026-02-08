"""Tests for orchestration engine."""

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
