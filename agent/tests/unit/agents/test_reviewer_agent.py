"""Tests for ReviewerAgent."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.agents.reviewer_agent import ReviewerAgent
from orchestrator.agents.base_agent import AgentRole, AgentState
from orchestrator.arch_registry import get_arch_profile
from orchestrator.llm.tools import REVIEWER_TOOLS


@pytest.fixture
def arch_profile():
    return get_arch_profile("x86_64")


@pytest.fixture
def mock_deps(arch_profile):
    return {
        "agent_id": "reviewer-01",
        "client": MagicMock(),
        "workspace": MagicMock(),
        "message_bus": MagicMock(),
        "kernel_spec_path": Path("/tmp/specs"),
        "arch_profile": arch_profile,
    }


@pytest.fixture
def reviewer(mock_deps):
    return ReviewerAgent(**mock_deps)


class TestReviewerInstantiation:
    def test_creation(self, reviewer):
        assert reviewer.agent_id == "reviewer-01"

    def test_role(self, reviewer):
        assert reviewer.role == AgentRole.REVIEWER

    def test_state_starts_idle(self, reviewer):
        assert reviewer.state == AgentState.IDLE

    def test_arch_profile(self, reviewer, arch_profile):
        assert reviewer.arch_profile is arch_profile


class TestReviewerTools:
    def test_tools_match_reviewer_tools(self, reviewer):
        assert reviewer.tools is REVIEWER_TOOLS

    def test_has_read_file(self, reviewer):
        tool_names = [t["function"]["name"] for t in reviewer.tools]
        assert "read_file" in tool_names

    def test_has_list_files(self, reviewer):
        tool_names = [t["function"]["name"] for t in reviewer.tools]
        assert "list_files" in tool_names

    def test_has_search_code(self, reviewer):
        tool_names = [t["function"]["name"] for t in reviewer.tools]
        assert "search_code" in tool_names

    def test_has_git_diff(self, reviewer):
        tool_names = [t["function"]["name"] for t in reviewer.tools]
        assert "git_diff" in tool_names

    def test_has_read_spec(self, reviewer):
        tool_names = [t["function"]["name"] for t in reviewer.tools]
        assert "read_spec" in tool_names

    def test_tool_count(self, reviewer):
        assert len(reviewer.tools) == len(REVIEWER_TOOLS)

    def test_no_write_file(self, reviewer):
        """Reviewer reads, does not write."""
        tool_names = [t["function"]["name"] for t in reviewer.tools]
        assert "write_file" not in tool_names

    def test_no_build_kernel(self, reviewer):
        tool_names = [t["function"]["name"] for t in reviewer.tools]
        assert "build_kernel" not in tool_names

    def test_no_shell(self, reviewer):
        tool_names = [t["function"]["name"] for t in reviewer.tools]
        assert "shell" not in tool_names


class TestReviewerSystemPrompt:
    def test_prompt_contains_arch(self, reviewer):
        assert "x86_64" in reviewer.system_prompt

    def test_prompt_mentions_reviewer(self, reviewer):
        assert "Reviewer" in reviewer.system_prompt

    def test_prompt_is_nonempty(self, reviewer):
        assert len(reviewer.system_prompt) > 0

    def test_fallback_arch_when_none(self):
        deps = {
            "agent_id": "rev-02",
            "client": MagicMock(),
            "workspace": MagicMock(),
            "message_bus": MagicMock(),
            "kernel_spec_path": Path("/tmp/specs"),
        }
        agent = ReviewerAgent(**deps)
        assert "x86_64" in agent.system_prompt
