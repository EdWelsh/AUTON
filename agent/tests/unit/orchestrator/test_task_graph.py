"""Tests for task graph."""

import pytest
from orchestrator.core.task_graph import TaskGraph, TaskState


def test_add_task():
    """Test adding a single task to the graph."""
    graph = TaskGraph()
    node = graph.add_task({
        "task_id": "boot-001",
        "title": "Implement boot loader",
        "subsystem": "boot",
        "assigned_to": "developer",
        "dependencies": [],
    })
    assert node.task_id == "boot-001"
    assert node.title == "Implement boot loader"
    assert node.state == TaskState.READY  # no deps -> ready


def test_add_tasks_with_dependencies():
    """Test adding multiple tasks with dependency ordering."""
    graph = TaskGraph()
    tasks = graph.add_tasks([
        {
            "task_id": "boot-001",
            "title": "Implement boot loader",
            "subsystem": "boot",
            "assigned_to": "developer",
            "dependencies": [],
        },
        {
            "task_id": "mm-001",
            "title": "Implement memory manager",
            "subsystem": "mm",
            "assigned_to": "developer",
            "dependencies": ["boot-001"],
        },
    ])
    assert len(tasks) == 2
    assert tasks[0].state == TaskState.READY
    assert tasks[1].state == TaskState.PENDING


def test_task_dependencies():
    """Test task dependency resolution after state transitions."""
    graph = TaskGraph()
    graph.add_tasks([
        {
            "task_id": "boot-001",
            "title": "Boot loader",
            "subsystem": "boot",
            "assigned_to": "developer",
            "dependencies": [],
        },
        {
            "task_id": "mm-001",
            "title": "Memory manager",
            "subsystem": "mm",
            "assigned_to": "developer",
            "dependencies": ["boot-001"],
        },
    ])
    boot = graph.get_task("boot-001")
    assert boot.dependencies == []

    graph.update_state("boot-001", TaskState.MERGED)
    mm = graph.get_task("mm-001")
    assert mm.state == TaskState.READY


def test_create_slm_training_tasks():
    """Test SLM task creation."""
    graph = TaskGraph()
    tasks = graph.create_slm_training_tasks("Train SLM")
    assert len(tasks) == 7
    assert tasks[0]["task_id"] == "slm-data-prep"


def test_topological_order():
    """Test topological ordering of tasks."""
    graph = TaskGraph()
    graph.add_tasks([
        {"task_id": "a", "title": "A", "dependencies": []},
        {"task_id": "b", "title": "B", "dependencies": ["a"]},
        {"task_id": "c", "title": "C", "dependencies": ["b"]},
    ])
    order = graph.topological_order()
    assert order.index("a") < order.index("b") < order.index("c")


def test_get_ready_tasks():
    """Ready tasks are returned sorted by priority."""
    graph = TaskGraph()
    graph.add_tasks([
        {"task_id": "low", "title": "Low", "dependencies": [], "priority": 5},
        {"task_id": "high", "title": "High", "dependencies": [], "priority": 1},
    ])
    ready = graph.get_ready_tasks()
    assert ready[0].task_id == "high"
    assert ready[1].task_id == "low"


def test_is_complete():
    """Graph is complete when all tasks are terminal."""
    graph = TaskGraph()
    graph.add_tasks([
        {"task_id": "a", "title": "A", "dependencies": []},
        {"task_id": "b", "title": "B", "dependencies": []},
    ])
    assert graph.is_complete is False
    graph.update_state("a", TaskState.MERGED)
    graph.update_state("b", TaskState.MERGED)
    assert graph.is_complete is True
