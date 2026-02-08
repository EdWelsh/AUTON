"""Tests for base agent."""

import pytest
from orchestrator.agents.base_agent import AgentRole, AgentState, TaskResult


def test_agent_role_enum():
    """Test AgentRole enum."""
    assert AgentRole.MANAGER.value == "manager"
    assert AgentRole.DEVELOPER.value == "developer"


def test_agent_state_enum():
    """Test AgentState enum."""
    assert AgentState.IDLE.value == "idle"
    assert AgentState.EXECUTING.value == "executing"


def test_task_result_creation():
    """Test TaskResult dataclass."""
    result = TaskResult(
        success=True,
        task_id="test-001",
        agent_id="dev-01",
        summary="Task completed",
    )
    assert result.success
    assert result.task_id == "test-001"
