"""The pluggable 'brain' that plans and drives the operator agent.

The brain is swappable by design (per the AUTON OS vision): a local model via
Ollama today, a cloud model when the user asks ("use ChatGPT"), or the on-device
SLM as the north-star. Provider selection is just a LiteLLM model string, so any
backend drives the same tools. When no model is reachable the runner falls back
to the deterministic planner (see planner.py) — the same neural→rule-engine
fallback AUTON uses throughout.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from .tools import ToolExecutor, tool_schemas

_REPO_ROOT = Path(__file__).resolve().parents[5]
_AGENT_CONFIG = _REPO_ROOT / "agent" / "config" / "auton.toml"

_SYSTEM = (
    "You are AUTON, an operating system you drive entirely from chat. The user "
    "gives a goal; you accomplish it by calling the provided tools, one step at a "
    "time, using each tool's result to decide the next step. Workspaces are "
    "sandboxed; refer to files by the names you saved them as. Sending email "
    "requires user confirmation — call send_email and the user is asked to approve. "
    "When the goal is complete, reply with a short summary of what you did."
)


class BrainUnavailable(Exception):
    """No usable model/provider — the runner should fall back to the planner."""


def resolve_model(request: str | None = None, default: str | None = None) -> str:
    """Pick a LiteLLM model string from an optional user request, else config.

    "use chatgpt"/"gpt" -> OpenAI; "claude"/"anthropic" -> Anthropic; otherwise
    the configured local Ollama model. This is how a user reconfigures the brain
    from chat.
    """
    text = (request or "").lower()
    if "chatgpt" in text or "gpt" in text or "openai" in text:
        return "openai/gpt-4o-mini"
    if "claude" in text or "anthropic" in text:
        return "anthropic/claude-sonnet-4-6"
    if default:
        return default
    return _config_model()


def _config_model() -> str:
    try:
        with open(_AGENT_CONFIG, "rb") as f:
            model = tomllib.load(f).get("llm", {}).get("model")
        if model:
            return model
    except (OSError, tomllib.TOMLDecodeError):
        pass
    return "ollama/llama3.1:8b"


def _ollama_api_base() -> str | None:
    try:
        with open(_AGENT_CONFIG, "rb") as f:
            return tomllib.load(f).get("llm", {}).get("endpoints", {}).get("ollama")
    except (OSError, tomllib.TOMLDecodeError):
        return None


class LLMBrain:
    """Agentic tool-calling loop over any LiteLLM-supported provider."""

    def __init__(self, model: str | None = None, max_turns: int = 10) -> None:
        self.model = model or _config_model()
        self.max_turns = max_turns

    def _litellm_model(self) -> str:
        # ollama_chat/ has the most reliable tool-calling support in LiteLLM.
        if self.model.startswith("ollama/"):
            return "ollama_chat/" + self.model.split("/", 1)[1]
        return self.model

    def run(self, goal: str, executor: ToolExecutor) -> str:
        try:
            import litellm
        except ImportError as exc:  # pragma: no cover - llm extra not installed
            raise BrainUnavailable("litellm not installed") from exc

        kwargs: dict = {"temperature": 0}
        if self.model.startswith("ollama"):
            base = _ollama_api_base()
            if base:
                kwargs["api_base"] = base

        messages: list[dict] = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": goal},
        ]
        tools = tool_schemas()
        try:
            for _ in range(self.max_turns):
                resp = litellm.completion(
                    model=self._litellm_model(), messages=messages, tools=tools, **kwargs
                )
                msg = resp.choices[0].message
                tool_calls = getattr(msg, "tool_calls", None)
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [tc.model_dump() for tc in tool_calls] if tool_calls else None,
                    }
                )
                if not tool_calls:
                    return msg.content or "(done)"
                for tc in tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    observation = executor.execute(tc.function.name, args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.function.name,
                            "content": observation,
                        }
                    )
        except Exception as exc:  # noqa: BLE001 - any provider/network error => fall back
            raise BrainUnavailable(str(exc)) from exc
        return "(reached max steps)"
