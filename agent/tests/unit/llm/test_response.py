"""Unit tests for orchestrator.llm.response module.

Tests ToolCall dataclass and LLMResponse including the from_litellm factory.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from orchestrator.llm.response import LLMResponse, ToolCall


# ---------------------------------------------------------------------------
# ToolCall
# ---------------------------------------------------------------------------


class TestToolCall:
    """Tests for the ToolCall dataclass."""

    def test_creation(self):
        tc = ToolCall(id="call-1", name="read_file", arguments={"path": "main.c"})
        assert tc.id == "call-1"
        assert tc.name == "read_file"
        assert tc.arguments == {"path": "main.c"}

    def test_creation_empty_arguments(self):
        tc = ToolCall(id="call-2", name="list_files", arguments={})
        assert tc.id == "call-2"
        assert tc.name == "list_files"
        assert tc.arguments == {}

    def test_creation_complex_arguments(self):
        args = {"path": "kernel/mm/page_alloc.c", "content": "void init() {}", "overwrite": True}
        tc = ToolCall(id="call-3", name="write_file", arguments=args)
        assert tc.arguments["path"] == "kernel/mm/page_alloc.c"
        assert tc.arguments["overwrite"] is True

    def test_equality(self):
        tc1 = ToolCall(id="call-1", name="read_file", arguments={"path": "a.c"})
        tc2 = ToolCall(id="call-1", name="read_file", arguments={"path": "a.c"})
        assert tc1 == tc2

    def test_inequality(self):
        tc1 = ToolCall(id="call-1", name="read_file", arguments={"path": "a.c"})
        tc2 = ToolCall(id="call-2", name="read_file", arguments={"path": "a.c"})
        assert tc1 != tc2


# ---------------------------------------------------------------------------
# LLMResponse
# ---------------------------------------------------------------------------


class TestLLMResponse:
    """Tests for the LLMResponse dataclass."""

    def test_creation_text_only(self):
        resp = LLMResponse(text="Hello world")
        assert resp.text == "Hello world"
        assert resp.tool_calls == []
        assert resp.finish_reason == "stop"
        assert resp.model == ""
        assert resp.raw is None

    def test_creation_with_tool_calls(self):
        tc = ToolCall(id="call-1", name="read_file", arguments={"path": "x.c"})
        resp = LLMResponse(text="Reading file.", tool_calls=[tc])
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "read_file"

    def test_creation_none_text(self):
        resp = LLMResponse(text=None)
        assert resp.text is None

    def test_creation_full(self):
        resp = LLMResponse(
            text="done",
            tool_calls=[],
            finish_reason="end_turn",
            model="anthropic/claude-opus-4-6",
            raw={"raw": True},
        )
        assert resp.finish_reason == "end_turn"
        assert resp.model == "anthropic/claude-opus-4-6"
        assert resp.raw == {"raw": True}


# ---------------------------------------------------------------------------
# LLMResponse.from_litellm
# ---------------------------------------------------------------------------


def _make_litellm_response(
    content: str | None = "Hello",
    tool_calls: list | None = None,
    finish_reason: str = "stop",
    model: str = "anthropic/claude-opus-4-6",
):
    """Build a mock LiteLLM ModelResponse with choices[0].message."""
    message = SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
    )
    choice = SimpleNamespace(
        message=message,
        finish_reason=finish_reason,
    )
    response = SimpleNamespace(
        choices=[choice],
        model=model,
    )
    return response


def _make_litellm_tool_call(tc_id: str, name: str, arguments: dict):
    """Build a mock LiteLLM tool call object."""
    return SimpleNamespace(
        id=tc_id,
        function=SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments),
        ),
    )


class TestLLMResponseFromLitellm:
    """Tests for the from_litellm class method."""

    def test_text_only_response(self):
        raw = _make_litellm_response(content="The answer is 42.")
        resp = LLMResponse.from_litellm(raw)

        assert resp.text == "The answer is 42."
        assert resp.tool_calls == []
        assert resp.finish_reason == "stop"
        assert resp.model == "anthropic/claude-opus-4-6"
        assert resp.raw is raw

    def test_none_content_becomes_none(self):
        raw = _make_litellm_response(content=None)
        resp = LLMResponse.from_litellm(raw)
        assert resp.text is None

    def test_empty_content_becomes_none(self):
        """Empty string is falsy so content='' should map to None."""
        raw = _make_litellm_response(content="")
        resp = LLMResponse.from_litellm(raw)
        assert resp.text is None

    def test_with_single_tool_call(self):
        tc = _make_litellm_tool_call("call-1", "read_file", {"path": "boot.asm"})
        raw = _make_litellm_response(content="Let me check.", tool_calls=[tc])
        resp = LLMResponse.from_litellm(raw)

        assert resp.text == "Let me check."
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].id == "call-1"
        assert resp.tool_calls[0].name == "read_file"
        assert resp.tool_calls[0].arguments == {"path": "boot.asm"}

    def test_with_multiple_tool_calls(self):
        tc1 = _make_litellm_tool_call("call-1", "read_file", {"path": "a.c"})
        tc2 = _make_litellm_tool_call("call-2", "write_file", {"path": "b.c", "content": "x"})
        raw = _make_litellm_response(content=None, tool_calls=[tc1, tc2])
        resp = LLMResponse.from_litellm(raw)

        assert resp.text is None
        assert len(resp.tool_calls) == 2
        assert resp.tool_calls[0].name == "read_file"
        assert resp.tool_calls[1].name == "write_file"
        assert resp.tool_calls[1].arguments["content"] == "x"

    def test_tool_call_with_invalid_json_arguments(self):
        """When arguments cannot be parsed as JSON, should default to empty dict."""
        tc = SimpleNamespace(
            id="call-bad",
            function=SimpleNamespace(
                name="shell",
                arguments="not valid json{{{",
            ),
        )
        raw = _make_litellm_response(content="trying", tool_calls=[tc])
        resp = LLMResponse.from_litellm(raw)

        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].id == "call-bad"
        assert resp.tool_calls[0].name == "shell"
        assert resp.tool_calls[0].arguments == {}

    def test_tool_call_with_none_arguments(self):
        """When arguments is None, json.loads raises TypeError -- should default to {}."""
        tc = SimpleNamespace(
            id="call-none",
            function=SimpleNamespace(
                name="build_kernel",
                arguments=None,
            ),
        )
        raw = _make_litellm_response(content=None, tool_calls=[tc])
        resp = LLMResponse.from_litellm(raw)

        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].arguments == {}

    def test_finish_reason_passthrough(self):
        raw = _make_litellm_response(finish_reason="tool_calls")
        resp = LLMResponse.from_litellm(raw)
        assert resp.finish_reason == "tool_calls"

    def test_finish_reason_none_defaults_to_stop(self):
        raw = _make_litellm_response(finish_reason=None)
        resp = LLMResponse.from_litellm(raw)
        assert resp.finish_reason == "stop"

    def test_model_passthrough(self):
        raw = _make_litellm_response(model="openai/gpt-4")
        resp = LLMResponse.from_litellm(raw)
        assert resp.model == "openai/gpt-4"

    def test_model_missing_attribute(self):
        """If response has no model attribute, should default to empty string."""
        message = SimpleNamespace(content="ok", tool_calls=None)
        choice = SimpleNamespace(message=message, finish_reason="stop")
        raw = SimpleNamespace(choices=[choice])
        # raw has no .model attribute
        resp = LLMResponse.from_litellm(raw)
        assert resp.model == ""

    def test_no_tool_calls_field_is_none(self):
        """message.tool_calls=None means no tool calls."""
        raw = _make_litellm_response(content="done", tool_calls=None)
        resp = LLMResponse.from_litellm(raw)
        assert resp.tool_calls == []

    def test_raw_preserved(self):
        raw = _make_litellm_response()
        resp = LLMResponse.from_litellm(raw)
        assert resp.raw is raw
