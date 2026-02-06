"""Claude API client with tool-use support for AUTON agents."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import anthropic

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Tracks token usage and estimated cost for an agent."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    # Approximate pricing per million tokens (Claude Opus 4.6)
    INPUT_COST_PER_M: float = 15.0
    OUTPUT_COST_PER_M: float = 75.0

    @property
    def estimated_cost_usd(self) -> float:
        return (
            self.input_tokens * self.INPUT_COST_PER_M / 1_000_000
            + self.output_tokens * self.OUTPUT_COST_PER_M / 1_000_000
        )

    def add(self, usage: anthropic.types.Usage) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        if hasattr(usage, "cache_read_input_tokens") and usage.cache_read_input_tokens:
            self.cache_read_tokens += usage.cache_read_input_tokens
        if hasattr(usage, "cache_creation_input_tokens") and usage.cache_creation_input_tokens:
            self.cache_write_tokens += usage.cache_creation_input_tokens


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


class ClaudeClient:
    """Async Claude API client with tool-use, rate limiting, and cost tracking."""

    def __init__(
        self,
        model: str = "claude-opus-4-6",
        max_tokens: int = 16384,
        api_key: str | None = None,
        cost_tracker: CostTracker | None = None,
    ):
        self.model = model
        self.max_tokens = max_tokens
        import httpx

        self.client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
            timeout=httpx.Timeout(300.0, connect=30.0),
            max_retries=3,
        )
        self.cost_tracker = cost_tracker or CostTracker()
        self._semaphore = asyncio.Semaphore(10)  # Max concurrent API calls
        self._last_call_time = 0.0
        self._min_interval = 0.1  # Minimum seconds between calls

    async def send_message(
        self,
        agent_id: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        model_override: str | None = None,
    ) -> anthropic.types.Message:
        """Send a message to Claude and return the response.

        Args:
            agent_id: Identifier for cost tracking.
            system: System prompt defining the agent's role.
            messages: Conversation history.
            tools: Tool definitions for tool use.
            temperature: Sampling temperature.
            model_override: Override the default model for this call.
        """
        self.cost_tracker.check_budget()

        async with self._semaphore:
            # Simple rate limiting
            now = time.monotonic()
            elapsed = now - self._last_call_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_call_time = time.monotonic()

            kwargs: dict[str, Any] = {
                "model": model_override or self.model,
                "max_tokens": self.max_tokens,
                "system": system,
                "messages": messages,
                "temperature": temperature,
            }
            if tools:
                kwargs["tools"] = tools

            try:
                response = await self.client.messages.create(**kwargs)
            except anthropic.RateLimitError:
                logger.warning("Rate limited, retrying in 30s for agent %s", agent_id)
                await asyncio.sleep(30)
                response = await self.client.messages.create(**kwargs)

            # Track usage
            usage = self.cost_tracker.get_agent_usage(agent_id)
            usage.add(response.usage)

            logger.debug(
                "Agent %s: %d input, %d output tokens (total cost: $%.4f)",
                agent_id,
                response.usage.input_tokens,
                response.usage.output_tokens,
                self.cost_tracker.total_cost_usd,
            )

            return response

    async def send_with_tools(
        self,
        agent_id: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_executor: Any,
        max_turns: int = 20,
        temperature: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Run an agentic tool-use loop until the model stops calling tools.

        Args:
            agent_id: Identifier for cost tracking.
            system: System prompt.
            messages: Initial conversation messages.
            tools: Tool definitions.
            tool_executor: Callable that executes tool calls and returns results.
            max_turns: Maximum number of tool-use turns before stopping.
            temperature: Sampling temperature.

        Returns:
            The full message history including tool calls and results.
        """
        messages = list(messages)  # Don't mutate the input

        for turn in range(max_turns):
            response = await self.send_message(
                agent_id=agent_id,
                system=system,
                messages=messages,
                tools=tools,
                temperature=temperature,
            )

            # Add assistant response to history
            messages.append({"role": "assistant", "content": response.content})

            # Check if the model wants to use tools
            if response.stop_reason != "tool_use":
                break

            # Execute all tool calls
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await tool_executor(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result),
                        }
                    )

            if tool_results:
                messages.append({"role": "user", "content": tool_results})
        else:
            logger.warning(
                "Agent %s hit max turns (%d) in tool-use loop", agent_id, max_turns
            )

        return messages
