"""Tests for ModelArchitectAgent."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.agents.model_architect_agent import ModelArchitectAgent
from orchestrator.agents.base_agent import AgentRole, AgentState
from orchestrator.arch_registry import get_arch_profile
from orchestrator.llm.tools import MODEL_ARCHITECT_TOOLS


@pytest.fixture
def arch_profile():
    return get_arch_profile("x86_64")


@pytest.fixture
def mock_deps(arch_profile):
    return {
        "agent_id": "model-arch-01",
        "client": MagicMock(),
        "workspace": MagicMock(),
        "message_bus": MagicMock(),
        "kernel_spec_path": Path("/tmp/specs"),
        "arch_profile": arch_profile,
    }


@pytest.fixture
def model_architect(mock_deps):
    return ModelArchitectAgent(**mock_deps)


class TestModelArchitectInstantiation:
    def test_creation(self, model_architect):
        assert model_architect.agent_id == "model-arch-01"

    def test_role(self, model_architect):
        assert model_architect.role == AgentRole.MODEL_ARCHITECT

    def test_state_starts_idle(self, model_architect):
        assert model_architect.state == AgentState.IDLE

    def test_arch_profile(self, model_architect, arch_profile):
        assert model_architect.arch_profile is arch_profile


class TestModelArchitectTools:
    def test_tools_match_model_architect_tools(self, model_architect):
        assert model_architect.tools is MODEL_ARCHITECT_TOOLS

    def test_has_read_file(self, model_architect):
        tool_names = [t["function"]["name"] for t in model_architect.tools]
        assert "read_file" in tool_names

    def test_has_write_file(self, model_architect):
        tool_names = [t["function"]["name"] for t in model_architect.tools]
        assert "write_file" in tool_names

    def test_has_list_files(self, model_architect):
        tool_names = [t["function"]["name"] for t in model_architect.tools]
        assert "list_files" in tool_names

    def test_has_validate_architecture(self, model_architect):
        tool_names = [t["function"]["name"] for t in model_architect.tools]
        assert "validate_architecture" in tool_names

    def test_has_estimate_flops(self, model_architect):
        tool_names = [t["function"]["name"] for t in model_architect.tools]
        assert "estimate_flops" in tool_names

    def test_has_shell(self, model_architect):
        tool_names = [t["function"]["name"] for t in model_architect.tools]
        assert "shell" in tool_names

    def test_tool_count(self, model_architect):
        assert len(model_architect.tools) == len(MODEL_ARCHITECT_TOOLS)

    def test_no_train_model(self, model_architect):
        """Model architect designs, does not train."""
        tool_names = [t["function"]["name"] for t in model_architect.tools]
        assert "train_model" not in tool_names

    def test_no_build_kernel(self, model_architect):
        tool_names = [t["function"]["name"] for t in model_architect.tools]
        assert "build_kernel" not in tool_names


class TestModelArchitectSystemPrompt:
    def test_prompt_contains_arch(self, model_architect):
        assert "x86_64" in model_architect.system_prompt

    def test_prompt_mentions_model_architect(self, model_architect):
        assert "Model Architect" in model_architect.system_prompt

    def test_prompt_mentions_transformer(self, model_architect):
        assert "transformer" in model_architect.system_prompt.lower()

    def test_prompt_is_nonempty(self, model_architect):
        assert len(model_architect.system_prompt) > 0
