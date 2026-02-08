"""Tests for task graph."""

import pytest
from orchestrator.core.task_graph import TaskGraph


def test_create_kernel_tasks():
    """Test kernel task creation."""
    graph = TaskGraph()
    tasks = graph.create_kernel_tasks("Build kernel")
    assert len(tasks) > 0
    assert tasks[0]["task_id"] == "boot-001"


def test_create_slm_training_tasks():
    """Test SLM task creation."""
    graph = TaskGraph()
    tasks = graph.create_slm_training_tasks("Train SLM")
    assert len(tasks) == 7
    assert tasks[0]["task_id"] == "slm-data-prep"


def test_task_dependencies():
    """Test task dependency ordering."""
    graph = TaskGraph()
    tasks = graph.create_kernel_tasks("Build kernel")
    boot_task = next(t for t in tasks if t["task_id"] == "boot-001")
    assert boot_task["dependencies"] == []
