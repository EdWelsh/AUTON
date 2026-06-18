"""Free-form natural language → capability, LLM-first with a rule fallback.

This mirrors the kernel's neural→rule-engine fallback (``slm/roles.c`` +
``slm/forward``): try the model first, and when there is no model, no key, or
no network, fall back to a deterministic keyword/substring-overlap score.

The public entry point is :func:`make_resolver`, which returns an
``IntentResolver`` (``Callable[[str, Registry], Capability | None]``) suitable
for ``Router(registry, intent_resolver=...)``. The Router only calls the
resolver when its own deterministic keyword match has already missed, so this
layer is the *semantic* second pass.

The agent LLM client (``orchestrator.llm.client.LLMClient``) is imported
lazily and optionally: this unit works even when ``orchestrator`` is not
installed, falling back to the deterministic path.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Callable

from controlplane.core import Capability, Registry

log = logging.getLogger(__name__)

# An intent resolver maps free-form text + the registry to a capability (or None).
IntentResolver = Callable[[str, Registry], "Capability | None"]

# Tokens too generic to carry intent; ignored when scoring keyword overlap so a
# stop word in a capability note can't outvote a real signal.
_STOP_WORDS = frozenset(
    {
        "a", "an", "and", "the", "to", "of", "for", "in", "on", "it", "this",
        "that", "my", "me", "please", "i", "so", "as", "is", "are", "be", "run",
        "manage", "with", "your", "into", "up", "out", "do", "can", "you",
    }
)

# Minimum overlap score required before the deterministic path claims a match.
# Below this we return None rather than guess (mirrors gibberish → no role).
_MIN_SCORE = 1

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    """Lowercase word tokens with stop words removed."""
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOP_WORDS}


def _score(text_tokens: set[str], cap: Capability) -> int:
    """Overlap score between the utterance and a capability's keywords + note.

    Keyword hits count double (they are the curated trigger surface); note-word
    hits count single. Substring hits on the raw text catch morphology like
    "containerize" → "container".
    """
    if not text_tokens:
        return 0

    score = 0
    raw = " ".join(text_tokens)

    for kw in cap.keywords:
        kw_l = kw.lower()
        if kw_l in text_tokens:
            score += 2
        elif kw_l in raw:  # substring, e.g. "container" in "containerize"
            score += 2
        else:
            # reverse substring: a token contains the keyword stem
            if any(kw_l in tok or tok in kw_l for tok in text_tokens if len(tok) > 3):
                score += 1

    note_tokens = _tokens(f"{cap.name} {cap.note}")
    score += len(text_tokens & note_tokens)
    return score


def deterministic_resolve(text: str, registry: Registry) -> Capability | None:
    """Best capability by keyword/substring/note overlap, or None.

    Offline, predictable, and dependency-free — this is the fallback used when
    no LLM is configured or reachable. Returns None when nothing scores above
    :data:`_MIN_SCORE` (e.g. gibberish or empty input).
    """
    text_tokens = _tokens(text)
    if not text_tokens:
        return None

    best: Capability | None = None
    best_score = 0
    for cap in registry.unique_by_name():
        s = _score(text_tokens, cap)
        if s > best_score:
            best_score = s
            best = cap

    if best_score < _MIN_SCORE:
        return None
    return best


_SYSTEM_PROMPT = (
    "You map a user's request to exactly one capability that can handle it.\n"
    "Reply with ONLY the capability name from the list, nothing else.\n"
    "If none fit, reply with the single word NONE."
)


def _build_user_prompt(text: str, caps: list[Capability]) -> str:
    lines = ["Capabilities:"]
    for cap in caps:
        lines.append(f"- {cap.name}: {cap.note}")
    lines.append("")
    lines.append(f"Request: {text}")
    lines.append("Capability name:")
    return "\n".join(lines)


def _match_name(reply: str, caps: list[Capability]) -> Capability | None:
    """Map a model's free-text reply back to a capability by name."""
    if not reply:
        return None
    cleaned = reply.strip().strip(".`\"'").lower()
    if not cleaned or cleaned == "none":
        return None
    by_name = {c.name.lower(): c for c in caps}
    # Exact name first, then a substring scan so "use docker" still resolves.
    if cleaned in by_name:
        return by_name[cleaned]
    for name, cap in by_name.items():
        if name in cleaned:
            return cap
    return None


def _import_llm_client():
    """Import the agent LLM client lazily; return (LLMClient, ProviderConfig) or None."""
    try:
        from orchestrator.llm.client import LLMClient, ProviderConfig
    except Exception as exc:  # noqa: BLE001 - optional dependency, any failure => fallback
        log.debug("orchestrator LLM client unavailable: %s", exc)
        return None
    return LLMClient, ProviderConfig


def make_resolver(
    model: str | None = None,
    api_keys: dict[str, str] | None = None,
    endpoints: dict[str, str] | None = None,
    agent_id: str = "controlplane-intent",
) -> IntentResolver:
    """Build an intent resolver: LLM-first when configured, else deterministic.

    Parameters
    ----------
    model:
        LiteLLM model string (e.g. ``"ollama/llama3.1:8b"``). When ``None`` the
        resolver is deterministic-only — useful offline and in tests.
    api_keys:
        Provider → API key, matching ``agent/config/auton.toml`` ``[llm.api_keys]``.
    endpoints:
        Provider → base URL, matching ``[llm.endpoints]`` (e.g.
        ``{"ollama": "http://localhost:11434"}``).
    agent_id:
        Identifier passed to the client for cost tracking.

    The returned callable never raises on the LLM path: any client/network
    error is logged and degrades to :func:`deterministic_resolve`, mirroring the
    kernel's neural→rule-engine fallback.
    """
    client = None
    if model:
        imported = _import_llm_client()
        if imported is not None:
            LLMClient, ProviderConfig = imported
            try:
                provider = ProviderConfig(
                    api_keys=dict(api_keys or {}),
                    endpoints=dict(endpoints or {}),
                )
                client = LLMClient(model=model, provider_config=provider)
            except Exception as exc:  # noqa: BLE001 - any setup failure => fallback
                log.warning("intent LLM client init failed, using fallback: %s", exc)
                client = None

    def resolve(text: str, registry: Registry) -> Capability | None:
        caps = registry.unique_by_name()
        if not caps:
            return None

        if client is not None:
            picked = _resolve_via_llm(client, agent_id, text, caps)
            if picked is not None:
                return picked
            # LLM returned NONE / unmatched / errored → deterministic backstop.

        return deterministic_resolve(text, registry)

    return resolve


def _resolve_via_llm(
    client,
    agent_id: str,
    text: str,
    caps: list[Capability],
) -> Capability | None:
    """One blocking LLM call mapping ``text`` to a capability name, or None.

    Swallows every error to the fallback path: a flaky model must never break
    routing. Runs the async client via ``asyncio.run`` so the resolver presents
    a plain synchronous ``Callable`` to the Router.
    """
    system = _SYSTEM_PROMPT
    user = _build_user_prompt(text, caps)
    messages = [{"role": "user", "content": user}]

    try:
        response = asyncio.run(
            client.send_message(
                agent_id=agent_id,
                system=system,
                messages=messages,
                temperature=0.0,
            )
        )
    except RuntimeError as exc:
        # Already inside a running loop (e.g. called from async code): use a
        # dedicated loop in a thread rather than failing.
        if "running event loop" in str(exc) or "cannot be called" in str(exc):
            return _resolve_via_llm_threaded(client, agent_id, system, messages, caps)
        log.warning("intent LLM call failed, using fallback: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001 - any model/network error => fallback
        log.warning("intent LLM call failed, using fallback: %s", exc)
        return None

    return _match_name(response.text or "", caps)


def _resolve_via_llm_threaded(
    client,
    agent_id: str,
    system: str,
    messages: list[dict[str, str]],
    caps: list[Capability],
) -> Capability | None:
    """Run the async call on a fresh loop in a worker thread (loop-safe path)."""
    import concurrent.futures

    def _run() -> str:
        return asyncio.run(
            client.send_message(
                agent_id=agent_id,
                system=system,
                messages=messages,
                temperature=0.0,
            )
        ).text or ""

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            reply = pool.submit(_run).result()
    except Exception as exc:  # noqa: BLE001
        log.warning("intent LLM threaded call failed, using fallback: %s", exc)
        return None
    return _match_name(reply, caps)
