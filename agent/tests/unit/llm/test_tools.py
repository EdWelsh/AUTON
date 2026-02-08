"""Unit tests for orchestrator.llm.tools module.

Tests individual tool definitions for correct structure and validates that
each agent-role tool set contains the expected tools with no duplicates.
"""

from __future__ import annotations

import pytest

from orchestrator.llm.tools import (
    # Individual tool definitions
    TOOL_ANALYZE_DATASET,
    TOOL_BUILD_KERNEL,
    TOOL_ESTIMATE_FLOPS,
    TOOL_EVALUATE_MODEL,
    TOOL_EXPORT_GGUF,
    TOOL_EXPORT_ONNX,
    TOOL_GIT_COMMIT,
    TOOL_GIT_DIFF,
    TOOL_INTEGRATE_SLM,
    TOOL_LIST_FILES,
    TOOL_QUANTIZE_MODEL,
    TOOL_READ_FILE,
    TOOL_READ_SPEC,
    TOOL_RUN_TEST,
    TOOL_SEARCH_CODE,
    TOOL_SHELL,
    TOOL_TOKENIZE_DATA,
    TOOL_TRAIN_MODEL,
    TOOL_VALIDATE_ARCHITECTURE,
    TOOL_WRITE_FILE,
    # Agent-role tool sets
    ARCHITECT_TOOLS,
    DATA_SCIENTIST_TOOLS,
    DEVELOPER_TOOLS,
    INTEGRATOR_TOOLS,
    MANAGER_TOOLS,
    MODEL_ARCHITECT_TOOLS,
    REVIEWER_TOOLS,
    TESTER_TOOLS,
    TRAINING_TOOLS,
)

# Collect every individual tool constant for parametrised structure tests.
ALL_TOOLS = [
    TOOL_READ_FILE,
    TOOL_WRITE_FILE,
    TOOL_SEARCH_CODE,
    TOOL_LIST_FILES,
    TOOL_BUILD_KERNEL,
    TOOL_RUN_TEST,
    TOOL_GIT_COMMIT,
    TOOL_GIT_DIFF,
    TOOL_READ_SPEC,
    TOOL_SHELL,
    TOOL_ANALYZE_DATASET,
    TOOL_TOKENIZE_DATA,
    TOOL_VALIDATE_ARCHITECTURE,
    TOOL_ESTIMATE_FLOPS,
    TOOL_TRAIN_MODEL,
    TOOL_EVALUATE_MODEL,
    TOOL_QUANTIZE_MODEL,
    TOOL_EXPORT_GGUF,
    TOOL_EXPORT_ONNX,
    TOOL_INTEGRATE_SLM,
]


def _tool_name(tool: dict) -> str:
    """Extract the function name from a tool dict for test IDs."""
    return tool["function"]["name"]


# ---------------------------------------------------------------------------
# Individual tool structure validation
# ---------------------------------------------------------------------------


class TestToolStructure:
    """Every tool dict must follow the OpenAI/LiteLLM function-calling schema."""

    @pytest.mark.parametrize("tool", ALL_TOOLS, ids=[_tool_name(t) for t in ALL_TOOLS])
    def test_has_type_function(self, tool):
        assert tool["type"] == "function"

    @pytest.mark.parametrize("tool", ALL_TOOLS, ids=[_tool_name(t) for t in ALL_TOOLS])
    def test_has_function_key(self, tool):
        assert "function" in tool
        assert isinstance(tool["function"], dict)

    @pytest.mark.parametrize("tool", ALL_TOOLS, ids=[_tool_name(t) for t in ALL_TOOLS])
    def test_function_has_name(self, tool):
        fn = tool["function"]
        assert "name" in fn
        assert isinstance(fn["name"], str)
        assert len(fn["name"]) > 0

    @pytest.mark.parametrize("tool", ALL_TOOLS, ids=[_tool_name(t) for t in ALL_TOOLS])
    def test_function_has_description(self, tool):
        fn = tool["function"]
        assert "description" in fn
        assert isinstance(fn["description"], str)
        assert len(fn["description"]) > 0

    @pytest.mark.parametrize("tool", ALL_TOOLS, ids=[_tool_name(t) for t in ALL_TOOLS])
    def test_function_has_parameters(self, tool):
        fn = tool["function"]
        assert "parameters" in fn
        params = fn["parameters"]
        assert isinstance(params, dict)
        assert params.get("type") == "object"
        assert "properties" in params

    @pytest.mark.parametrize("tool", ALL_TOOLS, ids=[_tool_name(t) for t in ALL_TOOLS])
    def test_required_is_list(self, tool):
        params = tool["function"]["parameters"]
        if "required" in params:
            assert isinstance(params["required"], list)
            # Every required field must exist in properties
            for req in params["required"]:
                assert req in params["properties"], (
                    f"Required field '{req}' not in properties for tool '{tool['function']['name']}'"
                )


# ---------------------------------------------------------------------------
# Specific tool name checks
# ---------------------------------------------------------------------------


class TestToolNames:
    """Spot-check that certain well-known tools have the expected names."""

    def test_read_file_name(self):
        assert TOOL_READ_FILE["function"]["name"] == "read_file"

    def test_write_file_name(self):
        assert TOOL_WRITE_FILE["function"]["name"] == "write_file"

    def test_search_code_name(self):
        assert TOOL_SEARCH_CODE["function"]["name"] == "search_code"

    def test_build_kernel_name(self):
        assert TOOL_BUILD_KERNEL["function"]["name"] == "build_kernel"

    def test_shell_name(self):
        assert TOOL_SHELL["function"]["name"] == "shell"

    def test_train_model_name(self):
        assert TOOL_TRAIN_MODEL["function"]["name"] == "train_model"

    def test_export_gguf_name(self):
        assert TOOL_EXPORT_GGUF["function"]["name"] == "export_gguf"

    def test_integrate_slm_name(self):
        assert TOOL_INTEGRATE_SLM["function"]["name"] == "integrate_slm"


# ---------------------------------------------------------------------------
# Tool set membership
# ---------------------------------------------------------------------------


def _names_in(tool_set: list[dict]) -> set[str]:
    """Return the set of function names in a tool set."""
    return {t["function"]["name"] for t in tool_set}


class TestManagerTools:
    def test_contains_expected_tools(self):
        names = _names_in(MANAGER_TOOLS)
        assert "read_spec" in names
        assert "list_files" in names
        assert "read_file" in names
        assert "search_code" in names

    def test_does_not_contain_write_tools(self):
        names = _names_in(MANAGER_TOOLS)
        assert "write_file" not in names
        assert "git_commit" not in names
        assert "shell" not in names


class TestArchitectTools:
    def test_contains_expected_tools(self):
        names = _names_in(ARCHITECT_TOOLS)
        assert "read_spec" in names
        assert "read_file" in names
        assert "write_file" in names
        assert "list_files" in names
        assert "search_code" in names

    def test_does_not_contain_build_tools(self):
        names = _names_in(ARCHITECT_TOOLS)
        assert "build_kernel" not in names
        assert "run_test" not in names


class TestDeveloperTools:
    def test_contains_expected_tools(self):
        names = _names_in(DEVELOPER_TOOLS)
        expected = {
            "read_spec", "read_file", "write_file", "list_files",
            "search_code", "build_kernel", "run_test", "git_commit",
            "git_diff", "shell",
        }
        assert expected.issubset(names)

    def test_count(self):
        assert len(DEVELOPER_TOOLS) == 10


class TestReviewerTools:
    def test_contains_expected_tools(self):
        names = _names_in(REVIEWER_TOOLS)
        assert "read_file" in names
        assert "git_diff" in names
        assert "read_spec" in names

    def test_does_not_contain_write_tools(self):
        names = _names_in(REVIEWER_TOOLS)
        assert "write_file" not in names
        assert "git_commit" not in names
        assert "shell" not in names


class TestTesterTools:
    def test_contains_expected_tools(self):
        names = _names_in(TESTER_TOOLS)
        assert "build_kernel" in names
        assert "run_test" in names
        assert "shell" in names
        assert "write_file" in names


class TestIntegratorTools:
    def test_contains_expected_tools(self):
        names = _names_in(INTEGRATOR_TOOLS)
        assert "build_kernel" in names
        assert "git_commit" in names
        assert "integrate_slm" in names
        assert "shell" in names


# ---------------------------------------------------------------------------
# SLM tool sets
# ---------------------------------------------------------------------------


class TestDataScientistTools:
    def test_contains_expected_tools(self):
        names = _names_in(DATA_SCIENTIST_TOOLS)
        assert "analyze_dataset" in names
        assert "tokenize_data" in names
        assert "read_file" in names
        assert "write_file" in names
        assert "shell" in names

    def test_does_not_contain_kernel_tools(self):
        names = _names_in(DATA_SCIENTIST_TOOLS)
        assert "build_kernel" not in names
        assert "run_test" not in names


class TestModelArchitectTools:
    def test_contains_expected_tools(self):
        names = _names_in(MODEL_ARCHITECT_TOOLS)
        assert "validate_architecture" in names
        assert "estimate_flops" in names
        assert "read_file" in names
        assert "write_file" in names
        assert "shell" in names

    def test_does_not_contain_training_tools(self):
        names = _names_in(MODEL_ARCHITECT_TOOLS)
        assert "train_model" not in names
        assert "quantize_model" not in names


class TestTrainingTools:
    def test_contains_expected_tools(self):
        names = _names_in(TRAINING_TOOLS)
        assert "train_model" in names
        assert "evaluate_model" in names
        assert "quantize_model" in names
        assert "export_gguf" in names
        assert "export_onnx" in names
        assert "shell" in names

    def test_does_not_contain_kernel_tools(self):
        names = _names_in(TRAINING_TOOLS)
        assert "build_kernel" not in names
        assert "run_test" not in names


# ---------------------------------------------------------------------------
# No duplicate tool names in any tool set
# ---------------------------------------------------------------------------


ALL_TOOL_SETS = {
    "MANAGER_TOOLS": MANAGER_TOOLS,
    "ARCHITECT_TOOLS": ARCHITECT_TOOLS,
    "DEVELOPER_TOOLS": DEVELOPER_TOOLS,
    "REVIEWER_TOOLS": REVIEWER_TOOLS,
    "TESTER_TOOLS": TESTER_TOOLS,
    "INTEGRATOR_TOOLS": INTEGRATOR_TOOLS,
    "DATA_SCIENTIST_TOOLS": DATA_SCIENTIST_TOOLS,
    "MODEL_ARCHITECT_TOOLS": MODEL_ARCHITECT_TOOLS,
    "TRAINING_TOOLS": TRAINING_TOOLS,
}


class TestNoDuplicateToolNames:
    @pytest.mark.parametrize(
        "set_name,tool_set",
        ALL_TOOL_SETS.items(),
        ids=ALL_TOOL_SETS.keys(),
    )
    def test_no_duplicate_names(self, set_name, tool_set):
        names = [t["function"]["name"] for t in tool_set]
        assert len(names) == len(set(names)), (
            f"Duplicate tool names found in {set_name}: "
            f"{[n for n in names if names.count(n) > 1]}"
        )
