"""Tests for base agent."""

import json

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.agents.base_agent import Agent, AgentRole, AgentState, TaskResult
from orchestrator.arch_registry import get_arch_profile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def arch_profile():
    return get_arch_profile("x86_64")


@pytest.fixture
def mock_deps(arch_profile):
    """Standard mock dependencies used by all Agent tests."""
    return {
        "agent_id": "base-01",
        "client": MagicMock(),
        "workspace": MagicMock(),
        "message_bus": MagicMock(),
        "kernel_spec_path": Path("/tmp/specs"),
        "arch_profile": arch_profile,
    }


@pytest.fixture
def base_agent(mock_deps, arch_profile):
    """Create a minimal Agent instance (base class, not a subclass)."""
    return Agent(
        role=AgentRole.DEVELOPER,
        system_prompt="test prompt",
        tools=[],
        **mock_deps,
    )


# ---------------------------------------------------------------------------
# AgentRole enum
# ---------------------------------------------------------------------------

class TestAgentRole:
    def test_manager_value(self):
        assert AgentRole.MANAGER.value == "manager"

    def test_architect_value(self):
        assert AgentRole.ARCHITECT.value == "architect"

    def test_developer_value(self):
        assert AgentRole.DEVELOPER.value == "developer"

    def test_reviewer_value(self):
        assert AgentRole.REVIEWER.value == "reviewer"

    def test_tester_value(self):
        assert AgentRole.TESTER.value == "tester"

    def test_integrator_value(self):
        assert AgentRole.INTEGRATOR.value == "integrator"

    def test_data_scientist_value(self):
        assert AgentRole.DATA_SCIENTIST.value == "data_scientist"

    def test_model_architect_value(self):
        assert AgentRole.MODEL_ARCHITECT.value == "model_architect"

    def test_training_value(self):
        assert AgentRole.TRAINING.value == "training"

    def test_role_count(self):
        """All 9 roles (including SLM roles) are present."""
        assert len(AgentRole) == 9

    def test_slm_roles_present(self):
        """The three SLM-specific roles exist."""
        slm_roles = {AgentRole.DATA_SCIENTIST, AgentRole.MODEL_ARCHITECT, AgentRole.TRAINING}
        assert len(slm_roles) == 3

    def test_role_is_str_enum(self):
        """AgentRole members should be usable as strings."""
        assert isinstance(AgentRole.MANAGER, str)
        assert AgentRole.MANAGER == "manager"


# ---------------------------------------------------------------------------
# AgentState enum
# ---------------------------------------------------------------------------

class TestAgentState:
    def test_idle(self):
        assert AgentState.IDLE.value == "idle"

    def test_thinking(self):
        assert AgentState.THINKING.value == "thinking"

    def test_executing(self):
        assert AgentState.EXECUTING.value == "executing"

    def test_waiting(self):
        assert AgentState.WAITING.value == "waiting"

    def test_done(self):
        assert AgentState.DONE.value == "done"

    def test_error(self):
        assert AgentState.ERROR.value == "error"

    def test_state_count(self):
        assert len(AgentState) == 6


# ---------------------------------------------------------------------------
# TaskResult
# ---------------------------------------------------------------------------

class TestTaskResult:
    def test_creation(self):
        result = TaskResult(
            success=True,
            task_id="test-001",
            agent_id="dev-01",
            summary="Task completed",
        )
        assert result.success is True
        assert result.task_id == "test-001"
        assert result.agent_id == "dev-01"
        assert result.summary == "Task completed"

    def test_defaults(self):
        result = TaskResult(
            success=False,
            task_id="t",
            agent_id="a",
            summary="s",
        )
        assert result.artifacts == []
        assert result.branch is None
        assert result.build_status == "unknown"
        assert result.test_status == "unknown"
        assert result.error is None

    def test_with_artifacts(self):
        result = TaskResult(
            success=True,
            task_id="t",
            agent_id="a",
            summary="done",
            artifacts=["kernel/mm/page.c", "kernel/mm/slab.c"],
        )
        assert len(result.artifacts) == 2
        assert "kernel/mm/page.c" in result.artifacts


# ---------------------------------------------------------------------------
# Agent instantiation
# ---------------------------------------------------------------------------

class TestAgentCreation:
    def test_basic_creation(self, base_agent):
        assert base_agent.agent_id == "base-01"
        assert base_agent.role == AgentRole.DEVELOPER
        assert base_agent.system_prompt == "test prompt"

    def test_state_starts_idle(self, base_agent):
        assert base_agent.state == AgentState.IDLE

    def test_conversation_starts_empty(self, base_agent):
        assert base_agent._conversation == []

    def test_client_assigned(self, base_agent):
        assert base_agent.client is not None

    def test_workspace_assigned(self, base_agent):
        assert base_agent.workspace is not None

    def test_message_bus_assigned(self, base_agent):
        assert base_agent.message_bus is not None

    def test_kernel_spec_path_assigned(self, base_agent):
        assert base_agent.kernel_spec_path == Path("/tmp/specs")

    def test_arch_profile_assigned(self, base_agent, arch_profile):
        assert base_agent.arch_profile is arch_profile
        assert base_agent.arch_profile.name == "x86_64"

    def test_model_override_default_none(self, base_agent):
        assert base_agent.model_override is None

    def test_model_override_explicit(self, mock_deps):
        agent = Agent(
            role=AgentRole.DEVELOPER,
            system_prompt="test",
            tools=[],
            model_override="gpt-4",
            **mock_deps,
        )
        assert agent.model_override == "gpt-4"

    def test_arch_profile_optional(self):
        """Agent can be created without arch_profile (defaults to None)."""
        agent = Agent(
            agent_id="no-arch-01",
            role=AgentRole.DEVELOPER,
            system_prompt="test",
            tools=[],
            client=MagicMock(),
            workspace=MagicMock(),
            message_bus=MagicMock(),
            kernel_spec_path=Path("/tmp/specs"),
        )
        assert agent.arch_profile is None


# ---------------------------------------------------------------------------
# _format_task_prompt
# ---------------------------------------------------------------------------

class TestFormatTaskPrompt:
    def test_title_only(self, base_agent):
        task = {"title": "Implement boot"}
        result = base_agent._format_task_prompt(task)
        assert "## Task: Implement boot" in result

    def test_unnamed_task(self, base_agent):
        result = base_agent._format_task_prompt({})
        assert "## Task: Unnamed task" in result

    def test_description_included(self, base_agent):
        task = {"title": "T", "description": "Build the page allocator"}
        result = base_agent._format_task_prompt(task)
        assert "Build the page allocator" in result

    def test_subsystem_included(self, base_agent):
        task = {"title": "T", "subsystem": "mm"}
        result = base_agent._format_task_prompt(task)
        assert "**Subsystem**: mm" in result

    def test_spec_reference_included(self, base_agent):
        task = {"title": "T", "spec_reference": "mm/page_alloc"}
        result = base_agent._format_task_prompt(task)
        assert "**Specification**: mm/page_alloc" in result

    def test_dependencies_included(self, base_agent):
        task = {"title": "T", "dependencies": ["boot-001", "mm-001"]}
        result = base_agent._format_task_prompt(task)
        assert "boot-001" in result
        assert "mm-001" in result

    def test_acceptance_criteria_included(self, base_agent):
        task = {
            "title": "T",
            "acceptance_criteria": ["Builds cleanly", "Tests pass"],
        }
        result = base_agent._format_task_prompt(task)
        assert "- Builds cleanly" in result
        assert "- Tests pass" in result

    def test_context_included(self, base_agent):
        task = {"title": "T", "context": "Use buddy allocator algorithm"}
        result = base_agent._format_task_prompt(task)
        assert "Use buddy allocator algorithm" in result

    def test_trailing_instruction(self, base_agent):
        result = base_agent._format_task_prompt({"title": "T"})
        assert "Execute this task using the tools available to you" in result

    def test_full_task(self, base_agent):
        task = {
            "title": "Implement page allocator",
            "description": "Write the buddy allocator.",
            "subsystem": "mm",
            "spec_reference": "mm/page_alloc",
            "dependencies": ["boot-001"],
            "acceptance_criteria": ["Tests pass"],
            "context": "Use 4K pages.",
        }
        result = base_agent._format_task_prompt(task)
        assert "## Task: Implement page allocator" in result
        assert "Write the buddy allocator." in result
        assert "**Subsystem**: mm" in result
        assert "**Specification**: mm/page_alloc" in result
        assert "boot-001" in result
        assert "- Tests pass" in result
        assert "Use 4K pages." in result


# ---------------------------------------------------------------------------
# _extract_final_text
# ---------------------------------------------------------------------------

class TestExtractFinalText:
    def test_single_assistant_message(self, base_agent):
        messages = [{"role": "assistant", "content": "Hello world"}]
        assert base_agent._extract_final_text(messages) == "Hello world"

    def test_returns_last_assistant_text(self, base_agent):
        messages = [
            {"role": "assistant", "content": "First"},
            {"role": "user", "content": "Question"},
            {"role": "assistant", "content": "Second"},
        ]
        assert base_agent._extract_final_text(messages) == "Second"

    def test_skips_non_assistant(self, base_agent):
        messages = [
            {"role": "user", "content": "Hi"},
        ]
        assert base_agent._extract_final_text(messages) == "No text response."

    def test_empty_messages(self, base_agent):
        assert base_agent._extract_final_text([]) == "No text response."

    def test_skips_empty_content(self, base_agent):
        messages = [
            {"role": "assistant", "content": "Good"},
            {"role": "assistant", "content": ""},
        ]
        assert base_agent._extract_final_text(messages) == "Good"

    def test_skips_non_string_content(self, base_agent):
        messages = [
            {"role": "assistant", "content": "Fallback"},
            {"role": "assistant", "content": [{"type": "tool_use"}]},
        ]
        assert base_agent._extract_final_text(messages) == "Fallback"


# ---------------------------------------------------------------------------
# _extract_artifacts
# ---------------------------------------------------------------------------

class TestExtractArtifacts:
    def test_no_tool_calls(self, base_agent):
        messages = [{"role": "assistant", "content": "done"}]
        assert base_agent._extract_artifacts(messages) == []

    def test_single_write_file(self, base_agent):
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps({"path": "kernel/boot.c", "content": "..."}),
                        }
                    }
                ],
            }
        ]
        artifacts = base_agent._extract_artifacts(messages)
        assert artifacts == ["kernel/boot.c"]

    def test_multiple_write_files(self, base_agent):
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps({"path": "a.c", "content": ""}),
                        }
                    },
                    {
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps({"path": "b.c", "content": ""}),
                        }
                    },
                ],
            }
        ]
        artifacts = base_agent._extract_artifacts(messages)
        assert artifacts == ["a.c", "b.c"]

    def test_ignores_non_write_tools(self, base_agent):
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"path": "foo.c"}),
                        }
                    }
                ],
            }
        ]
        assert base_agent._extract_artifacts(messages) == []

    def test_handles_invalid_json(self, base_agent):
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file",
                            "arguments": "not json",
                        }
                    }
                ],
            }
        ]
        # Should not crash; returns empty because no path extracted
        assert base_agent._extract_artifacts(messages) == []

    def test_ignores_user_messages(self, base_agent):
        messages = [
            {
                "role": "user",
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps({"path": "x.c", "content": ""}),
                        }
                    }
                ],
            }
        ]
        assert base_agent._extract_artifacts(messages) == []

    def test_across_multiple_messages(self, base_agent):
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps({"path": "first.c", "content": ""}),
                        }
                    },
                ],
            },
            {"role": "user", "content": "ok"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps({"path": "second.c", "content": ""}),
                        }
                    },
                ],
            },
        ]
        artifacts = base_agent._extract_artifacts(messages)
        assert artifacts == ["first.c", "second.c"]


# ---------------------------------------------------------------------------
# _read_spec
# ---------------------------------------------------------------------------

class TestReadSpec:
    def test_subsystem_spec(self, base_agent, tmp_path):
        base_agent.kernel_spec_path = tmp_path
        sub_dir = tmp_path / "subsystems"
        sub_dir.mkdir()
        spec_file = sub_dir / "mm.md"
        spec_file.write_text("# Memory Manager Spec", encoding="utf-8")

        assert base_agent._read_spec("mm") == "# Memory Manager Spec"

    def test_architecture_spec(self, base_agent, tmp_path):
        base_agent.kernel_spec_path = tmp_path
        spec_file = tmp_path / "architecture.md"
        spec_file.write_text("# Architecture", encoding="utf-8")

        assert base_agent._read_spec("architecture") == "# Architecture"

    def test_hal_spec(self, base_agent, tmp_path):
        base_agent.kernel_spec_path = tmp_path
        arch_dir = tmp_path / "arch"
        arch_dir.mkdir()
        spec_file = arch_dir / "hal.md"
        spec_file.write_text("# HAL Spec", encoding="utf-8")

        assert base_agent._read_spec("hal") == "# HAL Spec"

    def test_arch_specific_spec(self, base_agent, tmp_path):
        base_agent.kernel_spec_path = tmp_path
        arch_dir = tmp_path / "arch"
        arch_dir.mkdir()
        spec_file = arch_dir / "x86_64.md"
        spec_file.write_text("# x86_64 Spec", encoding="utf-8")

        assert base_agent._read_spec("arch/x86_64") == "# x86_64 Spec"

    def test_missing_spec(self, base_agent, tmp_path):
        base_agent.kernel_spec_path = tmp_path
        result = base_agent._read_spec("nonexistent")
        assert "Specification not found" in result

    def test_arch_riscv64_spec(self, base_agent, tmp_path):
        base_agent.kernel_spec_path = tmp_path
        arch_dir = tmp_path / "arch"
        arch_dir.mkdir()
        spec_file = arch_dir / "riscv64.md"
        spec_file.write_text("# RISC-V 64", encoding="utf-8")

        assert base_agent._read_spec("arch/riscv64") == "# RISC-V 64"
