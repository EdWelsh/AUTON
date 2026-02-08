"""Tests for TrainingAgent."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.agents.training_agent import TrainingAgent
from orchestrator.agents.base_agent import AgentRole, AgentState
from orchestrator.arch_registry import get_arch_profile
from orchestrator.llm.tools import TRAINING_TOOLS


@pytest.fixture
def arch_profile():
    return get_arch_profile("x86_64")


@pytest.fixture
def mock_deps(arch_profile):
    return {
        "agent_id": "train-01",
        "client": MagicMock(),
        "workspace": MagicMock(),
        "message_bus": MagicMock(),
        "kernel_spec_path": Path("/tmp/specs"),
        "arch_profile": arch_profile,
    }


@pytest.fixture
def trainer(mock_deps):
    return TrainingAgent(**mock_deps)


class TestTrainingInstantiation:
    def test_creation(self, trainer):
        assert trainer.agent_id == "train-01"

    def test_role(self, trainer):
        assert trainer.role == AgentRole.TRAINING

    def test_state_starts_idle(self, trainer):
        assert trainer.state == AgentState.IDLE

    def test_arch_profile(self, trainer, arch_profile):
        assert trainer.arch_profile is arch_profile


class TestTrainingTools:
    def test_tools_match_training_tools(self, trainer):
        assert trainer.tools is TRAINING_TOOLS

    def test_has_read_file(self, trainer):
        tool_names = [t["function"]["name"] for t in trainer.tools]
        assert "read_file" in tool_names

    def test_has_write_file(self, trainer):
        tool_names = [t["function"]["name"] for t in trainer.tools]
        assert "write_file" in tool_names

    def test_has_list_files(self, trainer):
        tool_names = [t["function"]["name"] for t in trainer.tools]
        assert "list_files" in tool_names

    def test_has_train_model(self, trainer):
        tool_names = [t["function"]["name"] for t in trainer.tools]
        assert "train_model" in tool_names

    def test_has_evaluate_model(self, trainer):
        tool_names = [t["function"]["name"] for t in trainer.tools]
        assert "evaluate_model" in tool_names

    def test_has_quantize_model(self, trainer):
        tool_names = [t["function"]["name"] for t in trainer.tools]
        assert "quantize_model" in tool_names

    def test_has_export_gguf(self, trainer):
        tool_names = [t["function"]["name"] for t in trainer.tools]
        assert "export_gguf" in tool_names

    def test_has_export_onnx(self, trainer):
        tool_names = [t["function"]["name"] for t in trainer.tools]
        assert "export_onnx" in tool_names

    def test_has_shell(self, trainer):
        tool_names = [t["function"]["name"] for t in trainer.tools]
        assert "shell" in tool_names

    def test_tool_count(self, trainer):
        assert len(trainer.tools) == len(TRAINING_TOOLS)

    def test_no_build_kernel(self, trainer):
        """Training agent trains models, does not build kernels."""
        tool_names = [t["function"]["name"] for t in trainer.tools]
        assert "build_kernel" not in tool_names

    def test_no_analyze_dataset(self, trainer):
        """Dataset analysis belongs to the DataScientist agent."""
        tool_names = [t["function"]["name"] for t in trainer.tools]
        assert "analyze_dataset" not in tool_names


class TestTrainingSystemPrompt:
    def test_prompt_contains_arch(self, trainer):
        assert "x86_64" in trainer.system_prompt

    def test_prompt_mentions_training(self, trainer):
        assert "Training" in trainer.system_prompt

    def test_prompt_mentions_pytorch(self, trainer):
        assert "PyTorch" in trainer.system_prompt

    def test_prompt_mentions_perplexity(self, trainer):
        assert "perplexity" in trainer.system_prompt.lower()

    def test_prompt_is_nonempty(self, trainer):
        assert len(trainer.system_prompt) > 0
