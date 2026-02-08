"""Tests for ManagerAgent."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.agents.manager_agent import ManagerAgent
from orchestrator.agents.base_agent import AgentRole, AgentState
from orchestrator.arch_registry import get_arch_profile
from orchestrator.llm.tools import MANAGER_TOOLS


@pytest.fixture
def arch_profile():
    return get_arch_profile("x86_64")


@pytest.fixture
def mock_deps(arch_profile):
    return {
        "agent_id": "manager-01",
        "client": MagicMock(),
        "workspace": MagicMock(),
        "message_bus": MagicMock(),
        "kernel_spec_path": Path("/tmp/specs"),
        "arch_profile": arch_profile,
    }


@pytest.fixture
def manager(mock_deps):
    return ManagerAgent(**mock_deps)


class TestManagerInstantiation:
    def test_creation(self, manager):
        assert manager.agent_id == "manager-01"

    def test_role(self, manager):
        assert manager.role == AgentRole.MANAGER

    def test_state_starts_idle(self, manager):
        assert manager.state == AgentState.IDLE

    def test_arch_profile(self, manager, arch_profile):
        assert manager.arch_profile is arch_profile


class TestManagerTools:
    def test_tools_match_manager_tools(self, manager):
        assert manager.tools is MANAGER_TOOLS

    def test_has_read_spec(self, manager):
        tool_names = [t["function"]["name"] for t in manager.tools]
        assert "read_spec" in tool_names

    def test_has_list_files(self, manager):
        tool_names = [t["function"]["name"] for t in manager.tools]
        assert "list_files" in tool_names

    def test_has_read_file(self, manager):
        tool_names = [t["function"]["name"] for t in manager.tools]
        assert "read_file" in tool_names

    def test_has_search_code(self, manager):
        tool_names = [t["function"]["name"] for t in manager.tools]
        assert "search_code" in tool_names

    def test_tool_count(self, manager):
        assert len(manager.tools) == len(MANAGER_TOOLS)

    def test_no_write_file(self, manager):
        """Manager should not have write_file -- it coordinates, not codes."""
        tool_names = [t["function"]["name"] for t in manager.tools]
        assert "write_file" not in tool_names

    def test_no_build_kernel(self, manager):
        tool_names = [t["function"]["name"] for t in manager.tools]
        assert "build_kernel" not in tool_names


class TestManagerSystemPrompt:
    def test_prompt_contains_arch(self, manager):
        assert "x86_64" in manager.system_prompt

    def test_prompt_is_nonempty(self, manager):
        assert len(manager.system_prompt) > 0

    def test_prompt_mentions_manager_role(self, manager):
        assert "Manager" in manager.system_prompt

    def test_fallback_arch_when_none(self):
        """When arch_profile is not provided, should fall back to x86_64."""
        deps = {
            "agent_id": "mgr-02",
            "client": MagicMock(),
            "workspace": MagicMock(),
            "message_bus": MagicMock(),
            "kernel_spec_path": Path("/tmp/specs"),
        }
        agent = ManagerAgent(**deps)
        assert "x86_64" in agent.system_prompt
