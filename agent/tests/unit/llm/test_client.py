"""Unit tests for orchestrator.llm.client module.

Tests TokenUsage, CostTracker, ProviderConfig, and LLMClient classes.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.llm.client import (
    BudgetExceededError,
    CostTracker,
    LLMClient,
    ProviderConfig,
    TokenUsage,
)
from orchestrator.llm.response import LLMResponse, ToolCall


# ---------------------------------------------------------------------------
# TokenUsage
# ---------------------------------------------------------------------------


class TestTokenUsage:
    """Tests for the TokenUsage dataclass."""

    def test_init_defaults(self):
        usage = TokenUsage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.total_cost_usd == 0.0

    def test_init_custom(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50, total_cost_usd=0.01)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_cost_usd == 0.01

    def test_estimated_cost_usd_property(self):
        usage = TokenUsage(total_cost_usd=1.25)
        assert usage.estimated_cost_usd == 1.25

    def test_add_with_mock_usage(self):
        usage = TokenUsage()
        mock_usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50)
        mock_response = MagicMock()

        with patch("orchestrator.llm.client.litellm") as mock_litellm:
            mock_litellm.completion_cost.return_value = 0.005
            usage.add(mock_usage, response=mock_response)

        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_cost_usd == pytest.approx(0.005)

    def test_add_accumulates_across_calls(self):
        usage = TokenUsage()
        usage_a = SimpleNamespace(prompt_tokens=100, completion_tokens=50)
        usage_b = SimpleNamespace(prompt_tokens=200, completion_tokens=80)
        resp_a = MagicMock()
        resp_b = MagicMock()

        with patch("orchestrator.llm.client.litellm") as mock_litellm:
            mock_litellm.completion_cost.side_effect = [0.01, 0.02]
            usage.add(usage_a, response=resp_a)
            usage.add(usage_b, response=resp_b)

        assert usage.input_tokens == 300
        assert usage.output_tokens == 130
        assert usage.total_cost_usd == pytest.approx(0.03)

    def test_add_none_token_handling(self):
        """When prompt_tokens or completion_tokens is None, treat as 0."""
        usage = TokenUsage()
        mock_usage = SimpleNamespace(prompt_tokens=None, completion_tokens=None)

        with patch("orchestrator.llm.client.litellm") as mock_litellm:
            mock_litellm.completion_cost.side_effect = Exception("no cost")
            usage.add(mock_usage, response=MagicMock())

        assert usage.input_tokens == 0
        assert usage.output_tokens == 0

    def test_add_missing_attributes_handled(self):
        """Usage object without prompt_tokens/completion_tokens attributes."""
        usage = TokenUsage()
        mock_usage = SimpleNamespace()  # no token attributes at all

        usage.add(mock_usage)
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0

    def test_add_without_response_skips_cost(self):
        """When response is None, cost should not be updated."""
        usage = TokenUsage()
        mock_usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)

        usage.add(mock_usage, response=None)
        assert usage.input_tokens == 10
        assert usage.output_tokens == 5
        assert usage.total_cost_usd == 0.0

    def test_add_cost_exception_is_suppressed(self):
        """When litellm.completion_cost raises, cost stays unchanged but tokens accumulate."""
        usage = TokenUsage()
        mock_usage = SimpleNamespace(prompt_tokens=42, completion_tokens=13)

        with patch("orchestrator.llm.client.litellm") as mock_litellm:
            mock_litellm.completion_cost.side_effect = RuntimeError("model not found")
            usage.add(mock_usage, response=MagicMock())

        assert usage.input_tokens == 42
        assert usage.output_tokens == 13
        assert usage.total_cost_usd == 0.0


# ---------------------------------------------------------------------------
# CostTracker
# ---------------------------------------------------------------------------


class TestCostTracker:
    """Tests for the CostTracker class."""

    def test_init_defaults(self):
        tracker = CostTracker()
        assert tracker.max_cost_usd == 50.0
        assert tracker.warn_at_usd == 25.0
        assert tracker.agent_usage == {}
        assert tracker._warned is False

    def test_init_custom_budgets(self):
        tracker = CostTracker(max_cost_usd=10.0, warn_at_usd=5.0)
        assert tracker.max_cost_usd == 10.0
        assert tracker.warn_at_usd == 5.0

    def test_get_agent_usage_creates_new(self):
        tracker = CostTracker()
        usage = tracker.get_agent_usage("agent-1")
        assert isinstance(usage, TokenUsage)
        assert usage.input_tokens == 0
        assert "agent-1" in tracker.agent_usage

    def test_get_agent_usage_returns_existing(self):
        tracker = CostTracker()
        usage_first = tracker.get_agent_usage("agent-1")
        usage_first.input_tokens = 999
        usage_second = tracker.get_agent_usage("agent-1")
        assert usage_second is usage_first
        assert usage_second.input_tokens == 999

    def test_total_cost_aggregation(self):
        tracker = CostTracker()
        u1 = tracker.get_agent_usage("agent-1")
        u1.total_cost_usd = 1.50
        u2 = tracker.get_agent_usage("agent-2")
        u2.total_cost_usd = 2.50
        assert tracker.total_cost_usd == pytest.approx(4.0)

    def test_total_cost_empty(self):
        tracker = CostTracker()
        assert tracker.total_cost_usd == 0.0

    def test_check_budget_raises_when_exceeded(self):
        tracker = CostTracker(max_cost_usd=5.0)
        u = tracker.get_agent_usage("agent-1")
        u.total_cost_usd = 5.0
        with pytest.raises(BudgetExceededError, match="exceeds budget"):
            tracker.check_budget()

    def test_check_budget_raises_when_over_budget(self):
        tracker = CostTracker(max_cost_usd=5.0)
        u = tracker.get_agent_usage("agent-1")
        u.total_cost_usd = 6.0
        with pytest.raises(BudgetExceededError):
            tracker.check_budget()

    def test_check_budget_ok_below_budget(self):
        tracker = CostTracker(max_cost_usd=10.0)
        u = tracker.get_agent_usage("agent-1")
        u.total_cost_usd = 3.0
        tracker.check_budget()  # should not raise

    def test_check_budget_warns_at_threshold(self, caplog):
        tracker = CostTracker(max_cost_usd=50.0, warn_at_usd=25.0)
        u = tracker.get_agent_usage("agent-1")
        u.total_cost_usd = 30.0

        with caplog.at_level(logging.WARNING, logger="orchestrator.llm.client"):
            tracker.check_budget()

        assert tracker._warned is True
        assert "Cost warning" in caplog.text

    def test_check_budget_warns_only_once(self, caplog):
        tracker = CostTracker(max_cost_usd=50.0, warn_at_usd=25.0)
        u = tracker.get_agent_usage("agent-1")
        u.total_cost_usd = 30.0

        with caplog.at_level(logging.WARNING, logger="orchestrator.llm.client"):
            tracker.check_budget()
            caplog.clear()
            tracker.check_budget()

        # The second call should not log again
        assert "Cost warning" not in caplog.text
        assert tracker._warned is True

    def test_check_budget_no_warn_below_threshold(self, caplog):
        tracker = CostTracker(max_cost_usd=50.0, warn_at_usd=25.0)
        u = tracker.get_agent_usage("agent-1")
        u.total_cost_usd = 10.0

        with caplog.at_level(logging.WARNING, logger="orchestrator.llm.client"):
            tracker.check_budget()

        assert tracker._warned is False
        assert "Cost warning" not in caplog.text


# ---------------------------------------------------------------------------
# ProviderConfig
# ---------------------------------------------------------------------------


class TestProviderConfig:
    """Tests for the ProviderConfig class."""

    def test_init_defaults(self):
        config = ProviderConfig()
        assert config.api_keys == {}
        assert config.endpoints == {}

    def test_get_api_key_with_provider_prefix(self):
        config = ProviderConfig(api_keys={"anthropic": "sk-ant-123"})
        assert config.get_api_key("anthropic/claude-opus-4-6") == "sk-ant-123"

    def test_get_api_key_without_provider_prefix(self):
        config = ProviderConfig(api_keys={"anthropic": "sk-ant-123"})
        assert config.get_api_key("claude-opus-4-6") is None

    def test_get_api_key_unknown_provider(self):
        config = ProviderConfig(api_keys={"anthropic": "sk-ant-123"})
        assert config.get_api_key("openai/gpt-4") is None

    def test_get_api_key_empty_config(self):
        config = ProviderConfig()
        assert config.get_api_key("anthropic/claude-opus-4-6") is None

    def test_get_base_url_with_provider(self):
        config = ProviderConfig(endpoints={"ollama": "http://localhost:11434"})
        assert config.get_base_url("ollama/llama3") == "http://localhost:11434"

    def test_get_base_url_without_provider_prefix(self):
        config = ProviderConfig(endpoints={"ollama": "http://localhost:11434"})
        assert config.get_base_url("llama3") is None

    def test_get_base_url_unknown_provider(self):
        config = ProviderConfig(endpoints={"ollama": "http://localhost:11434"})
        assert config.get_base_url("anthropic/claude-opus-4-6") is None

    def test_get_base_url_empty_config(self):
        config = ProviderConfig()
        assert config.get_base_url("ollama/llama3") is None

    def test_multiple_providers(self):
        config = ProviderConfig(
            api_keys={"anthropic": "sk-ant", "openai": "sk-oai"},
            endpoints={"ollama": "http://localhost:11434"},
        )
        assert config.get_api_key("anthropic/claude-opus-4-6") == "sk-ant"
        assert config.get_api_key("openai/gpt-4") == "sk-oai"
        assert config.get_base_url("ollama/llama3") == "http://localhost:11434"


# ---------------------------------------------------------------------------
# LLMClient
# ---------------------------------------------------------------------------


class TestLLMClient:
    """Tests for the LLMClient class."""

    def test_init_defaults(self):
        client = LLMClient()
        assert client.model == "anthropic/claude-opus-4-6"
        assert client.max_tokens == 16384
        assert isinstance(client.provider_config, ProviderConfig)
        assert isinstance(client.cost_tracker, CostTracker)

    def test_init_custom(self):
        pc = ProviderConfig(api_keys={"openai": "sk-test"})
        ct = CostTracker(max_cost_usd=100.0)
        client = LLMClient(
            model="openai/gpt-4",
            max_tokens=4096,
            provider_config=pc,
            cost_tracker=ct,
        )
        assert client.model == "openai/gpt-4"
        assert client.max_tokens == 4096
        assert client.provider_config is pc
        assert client.cost_tracker is ct

    @pytest.mark.asyncio
    async def test_send_with_tools_no_tool_calls(self):
        """When the model returns no tool_calls, the loop should exit after one turn."""
        client = LLMClient()

        mock_response = LLMResponse(
            text="I have finished the task.",
            tool_calls=[],
            finish_reason="stop",
        )

        with patch.object(client, "send_message", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response

            messages = [{"role": "user", "content": "Do something"}]
            tool_executor = AsyncMock()

            result = await client.send_with_tools(
                agent_id="test-agent",
                system="You are a test agent.",
                messages=messages,
                tools=[],
                tool_executor=tool_executor,
            )

        # send_message should be called once
        mock_send.assert_awaited_once()

        # tool_executor should never be called
        tool_executor.assert_not_awaited()

        # Result should contain original user message plus assistant reply
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "I have finished the task."
        assert "tool_calls" not in result[1]

    @pytest.mark.asyncio
    async def test_send_with_tools_single_tool_call(self):
        """When the model returns a tool call, the loop should execute it and continue."""
        client = LLMClient()

        tool_response = LLMResponse(
            text="Let me read that file.",
            tool_calls=[
                ToolCall(id="call-1", name="read_file", arguments={"path": "main.c"}),
            ],
        )
        final_response = LLMResponse(
            text="Done reading.",
            tool_calls=[],
        )

        with patch.object(client, "send_message", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = [tool_response, final_response]

            tool_executor = AsyncMock(return_value="file contents here")

            result = await client.send_with_tools(
                agent_id="test-agent",
                system="System prompt.",
                messages=[{"role": "user", "content": "Read main.c"}],
                tools=[{"type": "function", "function": {"name": "read_file"}}],
                tool_executor=tool_executor,
            )

        # Two send_message calls: first gets tool call, second gets final answer
        assert mock_send.await_count == 2

        # Tool executor called once
        tool_executor.assert_awaited_once_with("read_file", {"path": "main.c"})

        # Messages: user, assistant (with tool_calls), tool, assistant (final)
        assert len(result) == 4
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"
        assert "tool_calls" in result[1]
        assert result[2]["role"] == "tool"
        assert result[2]["tool_call_id"] == "call-1"
        assert result[2]["content"] == "file contents here"
        assert result[3]["role"] == "assistant"
        assert result[3]["content"] == "Done reading."

    @pytest.mark.asyncio
    async def test_send_with_tools_max_turns(self):
        """When tool calls keep coming, the loop respects max_turns."""
        client = LLMClient()

        infinite_tool_response = LLMResponse(
            text="Calling again...",
            tool_calls=[
                ToolCall(id="call-x", name="read_file", arguments={"path": "a.c"}),
            ],
        )

        with patch.object(client, "send_message", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = infinite_tool_response
            tool_executor = AsyncMock(return_value="ok")

            result = await client.send_with_tools(
                agent_id="test-agent",
                system="System prompt.",
                messages=[{"role": "user", "content": "loop"}],
                tools=[],
                tool_executor=tool_executor,
                max_turns=3,
            )

        # Should have been called exactly 3 times (max_turns)
        assert mock_send.await_count == 3

    @pytest.mark.asyncio
    async def test_send_message_checks_budget(self):
        """send_message should call check_budget before proceeding."""
        tracker = CostTracker(max_cost_usd=0.0)  # zero budget
        u = tracker.get_agent_usage("x")
        u.total_cost_usd = 1.0  # already over

        client = LLMClient(cost_tracker=tracker)

        with pytest.raises(BudgetExceededError):
            await client.send_message(
                agent_id="test",
                system="sys",
                messages=[{"role": "user", "content": "hi"}],
            )
