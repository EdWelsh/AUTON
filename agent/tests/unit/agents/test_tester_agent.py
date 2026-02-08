"""Tests for TesterAgent."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.agents.tester_agent import TesterAgent
from orchestrator.agents.base_agent import AgentRole, AgentState
from orchestrator.arch_registry import get_arch_profile
from orchestrator.llm.tools import TESTER_TOOLS


@pytest.fixture
def arch_profile():
    return get_arch_profile("x86_64")


@pytest.fixture
def mock_deps(arch_profile):
    return {
        "agent_id": "tester-01",
        "client": MagicMock(),
        "workspace": MagicMock(),
        "message_bus": MagicMock(),
        "kernel_spec_path": Path("/tmp/specs"),
        "arch_profile": arch_profile,
    }


@pytest.fixture
def tester(mock_deps):
    return TesterAgent(**mock_deps)


class TestTesterInstantiation:
    def test_creation(self, tester):
        assert tester.agent_id == "tester-01"

    def test_role(self, tester):
        assert tester.role == AgentRole.TESTER

    def test_state_starts_idle(self, tester):
        assert tester.state == AgentState.IDLE

    def test_arch_profile(self, tester, arch_profile):
        assert tester.arch_profile is arch_profile


class TestTesterTools:
    def test_tools_match_tester_tools(self, tester):
        assert tester.tools is TESTER_TOOLS

    def test_has_read_file(self, tester):
        tool_names = [t["function"]["name"] for t in tester.tools]
        assert "read_file" in tool_names

    def test_has_write_file(self, tester):
        tool_names = [t["function"]["name"] for t in tester.tools]
        assert "write_file" in tool_names

    def test_has_build_kernel(self, tester):
        tool_names = [t["function"]["name"] for t in tester.tools]
        assert "build_kernel" in tool_names

    def test_has_run_test(self, tester):
        tool_names = [t["function"]["name"] for t in tester.tools]
        assert "run_test" in tool_names

    def test_has_git_commit(self, tester):
        tool_names = [t["function"]["name"] for t in tester.tools]
        assert "git_commit" in tool_names

    def test_has_git_diff(self, tester):
        tool_names = [t["function"]["name"] for t in tester.tools]
        assert "git_diff" in tool_names

    def test_has_shell(self, tester):
        tool_names = [t["function"]["name"] for t in tester.tools]
        assert "shell" in tool_names

    def test_has_list_files(self, tester):
        tool_names = [t["function"]["name"] for t in tester.tools]
        assert "list_files" in tool_names

    def test_has_search_code(self, tester):
        tool_names = [t["function"]["name"] for t in tester.tools]
        assert "search_code" in tool_names

    def test_tool_count(self, tester):
        assert len(tester.tools) == len(TESTER_TOOLS)

    def test_no_read_spec(self, tester):
        """Tester does not need read_spec directly."""
        tool_names = [t["function"]["name"] for t in tester.tools]
        assert "read_spec" not in tool_names


class TestTesterSystemPrompt:
    def test_prompt_contains_arch(self, tester):
        assert "x86_64" in tester.system_prompt

    def test_prompt_mentions_tester(self, tester):
        assert "Tester" in tester.system_prompt

    def test_prompt_mentions_qemu(self, tester):
        assert "qemu-system-x86_64" in tester.system_prompt

    def test_prompt_is_nonempty(self, tester):
        assert len(tester.system_prompt) > 0

    def test_fallback_arch_when_none(self):
        deps = {
            "agent_id": "test-02",
            "client": MagicMock(),
            "workspace": MagicMock(),
            "message_bus": MagicMock(),
            "kernel_spec_path": Path("/tmp/specs"),
        }
        agent = TesterAgent(**deps)
        assert "x86_64" in agent.system_prompt
