"""Tests for ArchitectAgent."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.agents.architect_agent import ArchitectAgent
from orchestrator.agents.base_agent import AgentRole, AgentState
from orchestrator.arch_registry import get_arch_profile
from orchestrator.llm.tools import ARCHITECT_TOOLS


@pytest.fixture
def arch_profile():
    return get_arch_profile("x86_64")


@pytest.fixture
def mock_deps(arch_profile):
    return {
        "agent_id": "arch-01",
        "client": MagicMock(),
        "workspace": MagicMock(),
        "message_bus": MagicMock(),
        "kernel_spec_path": Path("/tmp/specs"),
        "arch_profile": arch_profile,
    }


@pytest.fixture
def architect(mock_deps):
    return ArchitectAgent(**mock_deps)


class TestArchitectInstantiation:
    def test_creation(self, architect):
        assert architect.agent_id == "arch-01"

    def test_role(self, architect):
        assert architect.role == AgentRole.ARCHITECT

    def test_state_starts_idle(self, architect):
        assert architect.state == AgentState.IDLE

    def test_arch_profile(self, architect, arch_profile):
        assert architect.arch_profile is arch_profile


class TestArchitectTools:
    def test_tools_match_architect_tools(self, architect):
        assert architect.tools is ARCHITECT_TOOLS

    def test_has_read_spec(self, architect):
        tool_names = [t["function"]["name"] for t in architect.tools]
        assert "read_spec" in tool_names

    def test_has_read_file(self, architect):
        tool_names = [t["function"]["name"] for t in architect.tools]
        assert "read_file" in tool_names

    def test_has_write_file(self, architect):
        tool_names = [t["function"]["name"] for t in architect.tools]
        assert "write_file" in tool_names

    def test_has_list_files(self, architect):
        tool_names = [t["function"]["name"] for t in architect.tools]
        assert "list_files" in tool_names

    def test_has_search_code(self, architect):
        tool_names = [t["function"]["name"] for t in architect.tools]
        assert "search_code" in tool_names

    def test_tool_count(self, architect):
        assert len(architect.tools) == len(ARCHITECT_TOOLS)

    def test_no_build_kernel(self, architect):
        """Architect designs interfaces, does not build."""
        tool_names = [t["function"]["name"] for t in architect.tools]
        assert "build_kernel" not in tool_names

    def test_no_shell(self, architect):
        tool_names = [t["function"]["name"] for t in architect.tools]
        assert "shell" not in tool_names


class TestArchitectSystemPrompt:
    def test_prompt_contains_arch(self, architect):
        assert "x86_64" in architect.system_prompt

    def test_prompt_mentions_architect(self, architect):
        assert "Architect" in architect.system_prompt

    def test_prompt_is_nonempty(self, architect):
        assert len(architect.system_prompt) > 0

    def test_fallback_arch_when_none(self):
        deps = {
            "agent_id": "arch-02",
            "client": MagicMock(),
            "workspace": MagicMock(),
            "message_bus": MagicMock(),
            "kernel_spec_path": Path("/tmp/specs"),
        }
        agent = ArchitectAgent(**deps)
        assert "x86_64" in agent.system_prompt
