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

from orchestrator.llm.response import LLMResponse

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
        if provider == "ollama_chat" and provider not in self.endpoints:
            # Same host, different LiteLLM route: `[llm.endpoints] ollama` covers both.
            return self.endpoints.get("ollama")
        return self.endpoints.get(provider)


class ModelTimeoutError(Exception):
    """A model call exceeded its request timeout.

    w12's second live run sat 17 minutes on an Ollama connection with nothing in
    flight at the server: an HTTP read with no timeout never returns. A named
    failure the engine can report beats a run that never ends.
    """


# Seconds one model call may take. A local 8B model answers a long agent prompt
# in well under this; a call past it is hung, not thinking.
DEFAULT_REQUEST_TIMEOUT = 600.0
# The asyncio backstop fires this long after the provider's own timeout, so
# the provider's (more informative) error wins when it does fire.
TIMEOUT_BACKSTOP_MARGIN = 30.0


class ModelUnavailableError(Exception):
    """The configured model does not exist on the configured provider."""


DEFAULT_OLLAMA_URL = "http://localhost:11434"
# A busy Ollama serving another request is not an absent one; a cold start must
# not be mistaken for a missing model, so the probe waits rather than guesses.
_OLLAMA_PROBE_TIMEOUT = 10.0
# One HTTP call to localhost per (endpoint, model) per process.
_preflight_ok: set[tuple[str, str]] = set()


def _installed_ollama_tags(base_url: str) -> set[str] | None:
    """Model tags installed on an Ollama host, or None if it is unreachable.

    Unreachable is deliberately not an error here: that is a different failure
    with its own message further down, and failing construction on it would
    make the orchestrator unusable whenever Ollama is merely slow to start.
    """
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"{base_url.rstrip('/')}/api/tags", timeout=_OLLAMA_PROBE_TIMEOUT
        ) as resp:
            payload = json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return {m["name"] for m in payload.get("models", []) if m.get("name")}


def preflight_model(model: str, provider_config: ProviderConfig) -> None:
    """Verify ``model`` exists on its provider before the first completion.

    Only ``ollama/*`` is checked here: a local tag can be missing with no
    credential involved, and the failure would otherwise surface as an empty
    completion or a connection error deep inside an agent run, long after the
    typo that caused it. Cloud providers are gated by the API-key check in
    :mod:`orchestrator.cli`, which is not duplicated here.
    """
    provider = model.split("/")[0] if "/" in model else ""
    if provider not in ("ollama", "ollama_chat"):
        return

    base_url = provider_config.get_base_url(model) or DEFAULT_OLLAMA_URL
    tag = model.split("/", 1)[1]
    if (base_url, tag) in _preflight_ok:
        return

    installed = _installed_ollama_tags(base_url)
    if installed is None:
        return  # endpoint down — a different failure, reported elsewhere
    if tag not in installed:
        available = ", ".join(sorted(installed)) or "(none installed)"
        raise ModelUnavailableError(
            f"Model {model!r} is not installed on the Ollama host at "
            f"{base_url}. Available: {available}. Either run "
            f"`ollama pull {tag}`, or set [llm].model in "
            f"config/auton.toml to one of the available names."
        )
    _preflight_ok.add((base_url, tag))


class LLMClient:
    """Async LLM client using LiteLLM for multi-provider support."""

    def __init__(
        self,
        model: str = "anthropic/claude-opus-4-6",
        max_tokens: int = 16384,
        provider_config: ProviderConfig | None = None,
        cost_tracker: CostTracker | None = None,
        preflight: bool = True,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.provider_config = provider_config or ProviderConfig()
        self.cost_tracker = cost_tracker or CostTracker()
        self._semaphore = asyncio.Semaphore(10)
        self._last_call_time = 0.0
        self._min_interval = 0.1
        self.request_timeout = request_timeout
        if preflight:
            preflight_model(self.model, self.provider_config)

    async def _complete(self, kwargs: dict[str, Any], agent_id: str) -> Any:
        """One model call, bounded. LiteLLM's own `timeout` is passed, and
        asyncio.wait_for backs it up, since not every provider path honours it."""
        kwargs = {**kwargs, "timeout": self.request_timeout}
        try:
            return await asyncio.wait_for(litellm.acompletion(**kwargs),
                                          timeout=self.request_timeout + TIMEOUT_BACKSTOP_MARGIN)
        except asyncio.TimeoutError as e:
            raise ModelTimeoutError(
                f"{kwargs.get('model')} did not answer {agent_id} within "
                f"{self.request_timeout:.0f}s") from e

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
                response = await self._complete(kwargs, agent_id)
            except litellm.RateLimitError:
                logger.warning("Rate limited, retrying in 30s for agent %s", agent_id)
                await asyncio.sleep(30)
                response = await self._complete(kwargs, agent_id)
            except (litellm.APIConnectionError, json.JSONDecodeError) as e:
                if "ollama" in model.lower():
                    logger.warning("Ollama JSON error, retrying with format=json: %s", e)
                    kwargs["format"] = "json"
                    response = await self._complete(kwargs, agent_id)
                else:
                    raise

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
