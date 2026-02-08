"""Unit tests for orchestrator.llm.prompts module.

Tests all 9 prompt builder functions to ensure they produce valid, non-empty
system prompts containing the architecture display_name.
"""

from __future__ import annotations

import pytest

from orchestrator.arch_registry import ArchProfile, get_arch_profile
from orchestrator.llm.prompts import (
    build_architect_prompt,
    build_data_scientist_prompt,
    build_developer_prompt,
    build_integrator_prompt,
    build_manager_prompt,
    build_model_architect_prompt,
    build_reviewer_prompt,
    build_tester_prompt,
    build_training_prompt,
)

# All 9 prompt builders mapped to their function for parametrised testing.
ALL_PROMPT_BUILDERS = [
    build_manager_prompt,
    build_architect_prompt,
    build_developer_prompt,
    build_reviewer_prompt,
    build_tester_prompt,
    build_integrator_prompt,
    build_data_scientist_prompt,
    build_model_architect_prompt,
    build_training_prompt,
]

# All supported architectures to test against.
ARCH_NAMES = ["x86_64", "aarch64", "riscv64"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(params=ARCH_NAMES, ids=ARCH_NAMES)
def arch_profile(request) -> ArchProfile:
    """Provide each registered ArchProfile as a parametrised fixture."""
    return get_arch_profile(request.param)


# ---------------------------------------------------------------------------
# Tests: each builder x each architecture
# ---------------------------------------------------------------------------


class TestPromptBuilders:
    """Tests applied to every prompt builder function."""

    @pytest.mark.parametrize("builder", ALL_PROMPT_BUILDERS, ids=lambda fn: fn.__name__)
    def test_returns_non_empty_string(self, builder, arch_profile):
        result = builder(arch_profile)
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.parametrize("builder", ALL_PROMPT_BUILDERS, ids=lambda fn: fn.__name__)
    def test_contains_arch_display_name(self, builder, arch_profile):
        result = builder(arch_profile)
        assert arch_profile.display_name in result


# ---------------------------------------------------------------------------
# Tests: individual prompt content checks
# ---------------------------------------------------------------------------


class TestManagerPrompt:
    def test_mentions_manager_role(self):
        arch = get_arch_profile("x86_64")
        prompt = build_manager_prompt(arch)
        assert "Manager" in prompt

    def test_mentions_task_coordination(self):
        arch = get_arch_profile("x86_64")
        prompt = build_manager_prompt(arch)
        assert "task" in prompt.lower()


class TestArchitectPrompt:
    def test_mentions_architect_role(self):
        arch = get_arch_profile("aarch64")
        prompt = build_architect_prompt(arch)
        assert "Architect" in prompt

    def test_mentions_interface_design(self):
        arch = get_arch_profile("aarch64")
        prompt = build_architect_prompt(arch)
        assert "interface" in prompt.lower() or "API" in prompt


class TestDeveloperPrompt:
    def test_mentions_developer_role(self):
        arch = get_arch_profile("x86_64")
        prompt = build_developer_prompt(arch)
        assert "Developer" in prompt

    def test_contains_arch_toolchain_info(self):
        arch = get_arch_profile("x86_64")
        prompt = build_developer_prompt(arch)
        assert arch.asm in prompt
        assert arch.boot_protocol in prompt

    def test_riscv_developer_prompt(self):
        arch = get_arch_profile("riscv64")
        prompt = build_developer_prompt(arch)
        assert arch.asm in prompt
        assert "sbi+dtb" in prompt


class TestReviewerPrompt:
    def test_mentions_reviewer_role(self):
        arch = get_arch_profile("riscv64")
        prompt = build_reviewer_prompt(arch)
        assert "Reviewer" in prompt

    def test_mentions_code_review(self):
        arch = get_arch_profile("riscv64")
        prompt = build_reviewer_prompt(arch)
        assert "review" in prompt.lower() or "Review" in prompt


class TestTesterPrompt:
    def test_mentions_tester_role(self):
        arch = get_arch_profile("x86_64")
        prompt = build_tester_prompt(arch)
        assert "Tester" in prompt

    def test_contains_qemu_info(self):
        arch = get_arch_profile("aarch64")
        prompt = build_tester_prompt(arch)
        assert arch.qemu in prompt
        assert arch.qemu_machine in prompt


class TestIntegratorPrompt:
    def test_mentions_integrator_role(self):
        arch = get_arch_profile("x86_64")
        prompt = build_integrator_prompt(arch)
        assert "Integrator" in prompt

    def test_mentions_merge(self):
        arch = get_arch_profile("x86_64")
        prompt = build_integrator_prompt(arch)
        assert "merge" in prompt.lower() or "Merge" in prompt


class TestDataScientistPrompt:
    def test_mentions_data_scientist_role(self):
        arch = get_arch_profile("x86_64")
        prompt = build_data_scientist_prompt(arch)
        assert "Data Scientist" in prompt

    def test_mentions_tokenization(self):
        arch = get_arch_profile("x86_64")
        prompt = build_data_scientist_prompt(arch)
        assert "tokeniz" in prompt.lower() or "Tokenize" in prompt


class TestModelArchitectPrompt:
    def test_mentions_model_architect_role(self):
        arch = get_arch_profile("riscv64")
        prompt = build_model_architect_prompt(arch)
        assert "Model Architect" in prompt

    def test_mentions_transformer(self):
        arch = get_arch_profile("riscv64")
        prompt = build_model_architect_prompt(arch)
        assert "transformer" in prompt.lower()

    def test_mentions_memory_constraints(self):
        arch = get_arch_profile("x86_64")
        prompt = build_model_architect_prompt(arch)
        assert "memory" in prompt.lower() or "Memory" in prompt


class TestTrainingPrompt:
    def test_mentions_training_role(self):
        arch = get_arch_profile("aarch64")
        prompt = build_training_prompt(arch)
        assert "Training" in prompt

    def test_mentions_pytorch(self):
        arch = get_arch_profile("aarch64")
        prompt = build_training_prompt(arch)
        assert "PyTorch" in prompt

    def test_mentions_checkpoint(self):
        arch = get_arch_profile("aarch64")
        prompt = build_training_prompt(arch)
        assert "checkpoint" in prompt.lower()

    def test_mentions_vibetensor(self):
        arch = get_arch_profile("x86_64")
        prompt = build_training_prompt(arch)
        assert "VibeTensor" in prompt
