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
from pathlib import Path

import tomllib

from .tools import ToolExecutor, tool_schemas


def _find_agent_config() -> Path:
    """Locate ``agent/config/auton.toml`` by walking up from this module.

    A fixed ``parents[N]`` index was off by one here, so the config was never
    actually read — every call fell through to a hardcoded default, which is
    how a dead model name went unnoticed. Searching is index-independent and
    survives a src-layout move.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "agent" / "config" / "auton.toml"
        if candidate.is_file():
            return candidate
    # Nothing found: return the conventional location so the error message
    # names a real path rather than silently picking a different config.
    return here.parents[4] / "agent" / "config" / "auton.toml"


_AGENT_CONFIG = _find_agent_config()

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
    """The configured model, or raise. Config is the only source of truth.

    A hardcoded fallback here would silently diverge from ``auton.toml`` the
    moment the config changed — which is exactly how a dead model name survived
    in two places. Raising instead lets the runner degrade to the rule brain.
    """
    try:
        with open(_AGENT_CONFIG, "rb") as f:
            model = tomllib.load(f).get("llm", {}).get("model")
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise BrainUnavailable(
            f"cannot read {_AGENT_CONFIG}: {exc}. Set [llm].model there to a "
            f"LiteLLM model string, e.g. 'ollama/gemma4:latest'."
        ) from exc
    if not model:
        raise BrainUnavailable(
            f"no [llm].model in {_AGENT_CONFIG}. Set it to a LiteLLM model "
            f"string, e.g. 'ollama/gemma4:latest'."
        )
    return model


def _ollama_api_base() -> str | None:
    try:
        with open(_AGENT_CONFIG, "rb") as f:
            return tomllib.load(f).get("llm", {}).get("endpoints", {}).get("ollama")
    except (OSError, tomllib.TOMLDecodeError):
        return None


# One HTTP call to localhost, cached per process: a preflight must not add
# latency to every turn. Keyed by (base_url, model) so a re-pull is picked up
# by a fresh process, not silently cached forever within one.
_PREFLIGHT_OK: set[tuple[str, str]] = set()


def preflight_ollama(model: str, api_base: str | None) -> None:
    """Fail fast if ``model`` is not installed on the Ollama host.

    Without this the symptom surfaces as an empty completion or a connection
    error several tool-calls into an agent run, where it reads as a flaky model
    rather than a typo. Raises :class:`BrainUnavailable` naming the model that
    was asked for and the ones that actually exist.
    """
    base = (api_base or "http://localhost:11434").rstrip("/")
    tag = model.split("/", 1)[1] if "/" in model else model
    if (base, tag) in _PREFLIGHT_OK:
        return

    installed = _installed_ollama_tags(base)
    if installed is None:
        # Endpoint unreachable: that is a different failure, and litellm will
        # report it with a better message than a guess from here.
        return
    if tag not in installed:
        available = ", ".join(sorted(installed)) or "(none installed)"
        raise BrainUnavailable(
            f"model {model!r} is not installed on the Ollama host at {base}. "
            f"Available: {available}. Either `ollama pull {tag}` or set "
            f"[llm].model in {_AGENT_CONFIG} to one of the available names."
        )
    _PREFLIGHT_OK.add((base, tag))


def _installed_ollama_tags(base: str) -> set[str] | None:
    """Installed model tags, or None when the endpoint cannot be reached.

    The timeout is generous: a busy Ollama serving another request is not the
    same as an absent one, and mistaking a cold start for absence would make
    the preflight itself the flaky part.
    """
    import json as _json
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=10) as resp:
            payload = _json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return {m["name"] for m in payload.get("models", []) if m.get("name")}


# One model call may not take longer than this. The fallback to the
# deterministic planner is the whole point of BrainUnavailable, and a call with
# no deadline can never reach it: an HTTP read that never returns raises
# nothing, so the runner waits instead of falling back. Matches
# DEFAULT_REQUEST_TIMEOUT in agent/orchestrator/llm/client.py, which already
# bounds its calls this way.
DEFAULT_REQUEST_TIMEOUT = 600.0


class LLMBrain:
    """Agentic tool-calling loop over any LiteLLM-supported provider."""

    def __init__(
        self,
        model: str | None = None,
        max_turns: int = 10,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        self.model = model or _config_model()
        self.max_turns = max_turns
        self.request_timeout = request_timeout

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

        kwargs: dict = {"temperature": 0, "timeout": self.request_timeout}
        if self.model.startswith("ollama"):
            base = _ollama_api_base()
            if base:
                kwargs["api_base"] = base
            preflight_ollama(self.model, base)

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
