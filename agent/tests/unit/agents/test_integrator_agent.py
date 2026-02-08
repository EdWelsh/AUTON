"""Tests for IntegratorAgent."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.agents.integrator_agent import IntegratorAgent
from orchestrator.agents.base_agent import AgentRole, AgentState
from orchestrator.arch_registry import get_arch_profile
from orchestrator.llm.tools import INTEGRATOR_TOOLS


@pytest.fixture
def arch_profile():
    return get_arch_profile("x86_64")


@pytest.fixture
def mock_deps(arch_profile):
    return {
        "agent_id": "integrator-01",
        "client": MagicMock(),
        "workspace": MagicMock(),
        "message_bus": MagicMock(),
        "kernel_spec_path": Path("/tmp/specs"),
        "arch_profile": arch_profile,
    }


@pytest.fixture
def integrator(mock_deps):
    return IntegratorAgent(**mock_deps)


class TestIntegratorInstantiation:
    def test_creation(self, integrator):
        assert integrator.agent_id == "integrator-01"

    def test_role(self, integrator):
        assert integrator.role == AgentRole.INTEGRATOR

    def test_state_starts_idle(self, integrator):
        assert integrator.state == AgentState.IDLE

    def test_arch_profile(self, integrator, arch_profile):
        assert integrator.arch_profile is arch_profile


class TestIntegratorTools:
    def test_tools_match_integrator_tools(self, integrator):
        assert integrator.tools is INTEGRATOR_TOOLS

    def test_has_read_file(self, integrator):
        tool_names = [t["function"]["name"] for t in integrator.tools]
        assert "read_file" in tool_names

    def test_has_write_file(self, integrator):
        tool_names = [t["function"]["name"] for t in integrator.tools]
        assert "write_file" in tool_names

    def test_has_build_kernel(self, integrator):
        tool_names = [t["function"]["name"] for t in integrator.tools]
        assert "build_kernel" in tool_names

    def test_has_run_test(self, integrator):
        tool_names = [t["function"]["name"] for t in integrator.tools]
        assert "run_test" in tool_names

    def test_has_git_commit(self, integrator):
        tool_names = [t["function"]["name"] for t in integrator.tools]
        assert "git_commit" in tool_names

    def test_has_git_diff(self, integrator):
        tool_names = [t["function"]["name"] for t in integrator.tools]
        assert "git_diff" in tool_names

    def test_has_shell(self, integrator):
        tool_names = [t["function"]["name"] for t in integrator.tools]
        assert "shell" in tool_names

    def test_has_list_files(self, integrator):
        tool_names = [t["function"]["name"] for t in integrator.tools]
        assert "list_files" in tool_names

    def test_has_search_code(self, integrator):
        tool_names = [t["function"]["name"] for t in integrator.tools]
        assert "search_code" in tool_names

    def test_has_integrate_slm(self, integrator):
        """Integrator has the SLM integration tool."""
        tool_names = [t["function"]["name"] for t in integrator.tools]
        assert "integrate_slm" in tool_names

    def test_tool_count(self, integrator):
        assert len(integrator.tools) == len(INTEGRATOR_TOOLS)


class TestIntegratorSystemPrompt:
    def test_prompt_contains_arch(self, integrator):
        assert "x86_64" in integrator.system_prompt

    def test_prompt_mentions_integrator(self, integrator):
        assert "Integrator" in integrator.system_prompt

    def test_prompt_is_nonempty(self, integrator):
        assert len(integrator.system_prompt) > 0

    def test_fallback_arch_when_none(self):
        deps = {
            "agent_id": "int-02",
            "client": MagicMock(),
            "workspace": MagicMock(),
            "message_bus": MagicMock(),
            "kernel_spec_path": Path("/tmp/specs"),
        }
        agent = IntegratorAgent(**deps)
        assert "x86_64" in agent.system_prompt
