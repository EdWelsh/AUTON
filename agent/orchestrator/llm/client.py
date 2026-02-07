"""LLM client with tool-use support for AUTON agents.

Uses LiteLLM for multi-provider support (Anthropic, OpenAI, Ollama, Gemini, etc.).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import litellm

from orchestrator.llm.response import LLMResponse, ToolCall

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Tracks token usage and estimated cost for an agent."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_cost_usd: float = 0.0

    @property
    def estimated_cost_usd(self) -> float:
        return self.total_cost_usd

    def add(self, usage, response=None) -> None:
        """Add usage from a LiteLLM response.

        Args:
            usage: The usage object (has prompt_tokens, completion_tokens).
            response: The full response, used for litellm.completion_cost().
        """
        self.input_tokens += getattr(usage, "prompt_tokens", 0) or 0
        self.output_tokens += getattr(usage, "completion_tokens", 0) or 0
        if response is not None:
            try:
                cost = litellm.completion_cost(completion_response=response)
                self.total_cost_usd += cost
            except Exception:
                pass


@dataclass
class CostTracker:
    """Global cost tracker across all agents."""

    max_cost_usd: float = 50.0
    warn_at_usd: float = 25.0
    agent_usage: dict[str, TokenUsage] = field(default_factory=dict)
    _warned: bool = False

    @property
    def total_cost_usd(self) -> float:
        return sum(u.estimated_cost_usd for u in self.agent_usage.values())

    def get_agent_usage(self, agent_id: str) -> TokenUsage:
        if agent_id not in self.agent_usage:
            self.agent_usage[agent_id] = TokenUsage()
        return self.agent_usage[agent_id]

    def check_budget(self) -> None:
        total = self.total_cost_usd
        if total >= self.max_cost_usd:
            raise BudgetExceededError(
                f"Total cost ${total:.2f} exceeds budget ${self.max_cost_usd:.2f}"
            )
        if not self._warned and total >= self.warn_at_usd:
            logger.warning("Cost warning: $%.2f of $%.2f budget used", total, self.max_cost_usd)
            self._warned = True


class BudgetExceededError(Exception):
    pass


@dataclass
class ProviderConfig:
    """Resolves API keys and base URLs for LiteLLM model strings."""

    api_keys: dict[str, str] = field(default_factory=dict)
    endpoints: dict[str, str] = field(default_factory=dict)

    def get_api_key(self, model: str) -> str | None:
        provider = model.split("/")[0] if "/" in model else ""
        return self.api_keys.get(provider)

    def get_base_url(self, model: str) -> str | None:
        provider = model.split("/")[0] if "/" in model else ""
        return self.endpoints.get(provider)


class LLMClient:
    """Async LLM client using LiteLLM for multi-provider support."""

    def __init__(
        self,
        model: str = "anthropic/claude-opus-4-6",
        max_tokens: int = 16384,
        provider_config: ProviderConfig | None = None,
        cost_tracker: CostTracker | None = None,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.provider_config = provider_config or ProviderConfig()
        self.cost_tracker = cost_tracker or CostTracker()
        self._semaphore = asyncio.Semaphore(10)
        self._last_call_time = 0.0
        self._min_interval = 0.1

    async def send_message(
        self,
        agent_id: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        model_override: str | None = None,
    ) -> LLMResponse:
        """Send a message to an LLM and return a provider-agnostic response."""
        self.cost_tracker.check_budget()

        model = model_override or self.model

        async with self._semaphore:
            now = time.monotonic()
            elapsed = now - self._last_call_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_call_time = time.monotonic()

            full_messages = [{"role": "system", "content": system}] + messages

            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": self.max_tokens,
                "messages": full_messages,
                "temperature": temperature,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            api_key = self.provider_config.get_api_key(model)
            if api_key:
                kwargs["api_key"] = api_key
            base_url = self.provider_config.get_base_url(model)
            if base_url:
                kwargs["api_base"] = base_url

            try:
                response = await litellm.acompletion(**kwargs)
            except litellm.RateLimitError:
                logger.warning("Rate limited, retrying in 30s for agent %s", agent_id)
                await asyncio.sleep(30)
                response = await litellm.acompletion(**kwargs)

            usage_tracker = self.cost_tracker.get_agent_usage(agent_id)
            if response.usage:
                usage_tracker.add(response.usage, response=response)

            logger.debug(
                "Agent %s: %d input, %d output tokens (total cost: $%.4f)",
                agent_id,
                getattr(response.usage, "prompt_tokens", 0) or 0,
                getattr(response.usage, "completion_tokens", 0) or 0,
                self.cost_tracker.total_cost_usd,
            )

            return LLMResponse.from_litellm(response)

    async def send_with_tools(
        self,
        agent_id: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_executor: Any,
        max_turns: int = 20,
        temperature: float = 0.0,
        model_override: str | None = None,
    ) -> list[dict[str, Any]]:
        """Run an agentic tool-use loop until the model stops calling tools."""
        messages = list(messages)

        for turn in range(max_turns):
            response = await self.send_message(
                agent_id=agent_id,
                system=system,
                messages=messages,
                tools=tools,
                temperature=temperature,
                model_override=model_override,
            )

            assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.text}
            if response.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in response.tool_calls
                ]
            messages.append(assistant_msg)

            if not response.tool_calls:
                break

            for tc in response.tool_calls:
                result = await tool_executor(tc.name, tc.arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result),
                })
        else:
            logger.warning(
                "Agent %s hit max turns (%d) in tool-use loop", agent_id, max_turns
            )

        return messages
