"""Tests for DataScientistAgent."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.agents.data_scientist_agent import DataScientistAgent
from orchestrator.agents.base_agent import AgentRole, AgentState
from orchestrator.arch_registry import get_arch_profile
from orchestrator.llm.tools import DATA_SCIENTIST_TOOLS


@pytest.fixture
def arch_profile():
    return get_arch_profile("x86_64")


@pytest.fixture
def mock_deps(arch_profile):
    return {
        "agent_id": "ds-01",
        "client": MagicMock(),
        "workspace": MagicMock(),
        "message_bus": MagicMock(),
        "kernel_spec_path": Path("/tmp/specs"),
        "arch_profile": arch_profile,
    }


@pytest.fixture
def data_scientist(mock_deps):
    return DataScientistAgent(**mock_deps)


class TestDataScientistInstantiation:
    def test_creation(self, data_scientist):
        assert data_scientist.agent_id == "ds-01"

    def test_role(self, data_scientist):
        assert data_scientist.role == AgentRole.DATA_SCIENTIST

    def test_state_starts_idle(self, data_scientist):
        assert data_scientist.state == AgentState.IDLE

    def test_arch_profile(self, data_scientist, arch_profile):
        assert data_scientist.arch_profile is arch_profile


class TestDataScientistTools:
    def test_tools_match_data_scientist_tools(self, data_scientist):
        assert data_scientist.tools is DATA_SCIENTIST_TOOLS

    def test_has_read_file(self, data_scientist):
        tool_names = [t["function"]["name"] for t in data_scientist.tools]
        assert "read_file" in tool_names

    def test_has_write_file(self, data_scientist):
        tool_names = [t["function"]["name"] for t in data_scientist.tools]
        assert "write_file" in tool_names

    def test_has_list_files(self, data_scientist):
        tool_names = [t["function"]["name"] for t in data_scientist.tools]
        assert "list_files" in tool_names

    def test_has_analyze_dataset(self, data_scientist):
        tool_names = [t["function"]["name"] for t in data_scientist.tools]
        assert "analyze_dataset" in tool_names

    def test_has_tokenize_data(self, data_scientist):
        tool_names = [t["function"]["name"] for t in data_scientist.tools]
        assert "tokenize_data" in tool_names

    def test_has_shell(self, data_scientist):
        tool_names = [t["function"]["name"] for t in data_scientist.tools]
        assert "shell" in tool_names

    def test_tool_count(self, data_scientist):
        assert len(data_scientist.tools) == len(DATA_SCIENTIST_TOOLS)

    def test_no_build_kernel(self, data_scientist):
        """Data scientist does not build kernels."""
        tool_names = [t["function"]["name"] for t in data_scientist.tools]
        assert "build_kernel" not in tool_names

    def test_no_train_model(self, data_scientist):
        """Data scientist prepares data, does not train models."""
        tool_names = [t["function"]["name"] for t in data_scientist.tools]
        assert "train_model" not in tool_names


class TestDataScientistSystemPrompt:
    def test_prompt_contains_arch(self, data_scientist):
        assert "x86_64" in data_scientist.system_prompt

    def test_prompt_mentions_data_scientist(self, data_scientist):
        assert "Data Scientist" in data_scientist.system_prompt

    def test_prompt_mentions_tokenize(self, data_scientist):
        prompt_lower = data_scientist.system_prompt.lower()
        assert "tokenize" in prompt_lower or "tokeniz" in prompt_lower

    def test_prompt_is_nonempty(self, data_scientist):
        assert len(data_scientist.system_prompt) > 0
