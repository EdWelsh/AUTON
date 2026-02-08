"""Tests for DeveloperAgent."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.agents.developer_agent import DeveloperAgent
from orchestrator.agents.base_agent import AgentRole, AgentState
from orchestrator.arch_registry import get_arch_profile
from orchestrator.llm.tools import DEVELOPER_TOOLS


@pytest.fixture
def arch_profile():
    return get_arch_profile("x86_64")


@pytest.fixture
def mock_deps(arch_profile):
    return {
        "agent_id": "dev-01",
        "client": MagicMock(),
        "workspace": MagicMock(),
        "message_bus": MagicMock(),
        "kernel_spec_path": Path("/tmp/specs"),
        "arch_profile": arch_profile,
    }


@pytest.fixture
def developer(mock_deps):
    return DeveloperAgent(**mock_deps)


class TestDeveloperInstantiation:
    def test_creation(self, developer):
        assert developer.agent_id == "dev-01"

    def test_role(self, developer):
        assert developer.role == AgentRole.DEVELOPER

    def test_state_starts_idle(self, developer):
        assert developer.state == AgentState.IDLE

    def test_arch_profile(self, developer, arch_profile):
        assert developer.arch_profile is arch_profile


class TestDeveloperTools:
    def test_tools_match_developer_tools(self, developer):
        assert developer.tools is DEVELOPER_TOOLS

    def test_has_read_spec(self, developer):
        tool_names = [t["function"]["name"] for t in developer.tools]
        assert "read_spec" in tool_names

    def test_has_read_file(self, developer):
        tool_names = [t["function"]["name"] for t in developer.tools]
        assert "read_file" in tool_names

    def test_has_write_file(self, developer):
        tool_names = [t["function"]["name"] for t in developer.tools]
        assert "write_file" in tool_names

    def test_has_build_kernel(self, developer):
        tool_names = [t["function"]["name"] for t in developer.tools]
        assert "build_kernel" in tool_names

    def test_has_run_test(self, developer):
        tool_names = [t["function"]["name"] for t in developer.tools]
        assert "run_test" in tool_names

    def test_has_git_commit(self, developer):
        tool_names = [t["function"]["name"] for t in developer.tools]
        assert "git_commit" in tool_names

    def test_has_git_diff(self, developer):
        tool_names = [t["function"]["name"] for t in developer.tools]
        assert "git_diff" in tool_names

    def test_has_shell(self, developer):
        tool_names = [t["function"]["name"] for t in developer.tools]
        assert "shell" in tool_names

    def test_has_list_files(self, developer):
        tool_names = [t["function"]["name"] for t in developer.tools]
        assert "list_files" in tool_names

    def test_has_search_code(self, developer):
        tool_names = [t["function"]["name"] for t in developer.tools]
        assert "search_code" in tool_names

    def test_tool_count(self, developer):
        assert len(developer.tools) == len(DEVELOPER_TOOLS)


class TestDeveloperSystemPrompt:
    def test_prompt_contains_arch(self, developer):
        assert "x86_64" in developer.system_prompt

    def test_prompt_mentions_developer(self, developer):
        assert "Developer" in developer.system_prompt

    def test_prompt_mentions_boot_protocol(self, developer):
        assert "multiboot2" in developer.system_prompt

    def test_prompt_mentions_assembler(self, developer):
        assert "nasm" in developer.system_prompt

    def test_prompt_is_nonempty(self, developer):
        assert len(developer.system_prompt) > 0

    def test_fallback_arch_when_none(self):
        deps = {
            "agent_id": "dev-02",
            "client": MagicMock(),
            "workspace": MagicMock(),
            "message_bus": MagicMock(),
            "kernel_spec_path": Path("/tmp/specs"),
        }
        agent = DeveloperAgent(**deps)
        assert "x86_64" in agent.system_prompt
