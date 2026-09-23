"""Is the local Ollama endpoint reachable *and* free enough to answer?

Shared because two suites needed it and both got it wrong the same way: they
checked ``/api/tags``, which answers in milliseconds no matter how loaded the
server is, and then made a real inference call behind it. Ollama serialises
requests per model, so on a machine already generating with a 27B model that
call sits in a queue. The agent client bounds it at 600s and retries once, so
the observed cost of one "guarded" test was twenty minutes -- and then a
failure caused by the queue rather than by the model being wrong.

So the probe asks for the smallest real piece of work there is -- one token --
and puts a deadline on it. That measures the thing the test actually cares
about, because the trivial request queues exactly where the real one would.

A cold model pays its load time inside this probe, which can legitimately
exceed the default deadline the first time. That is a skip, not a failure, and
an immediate re-run passes because the model stays resident. Trading a rare
false skip for a bounded suite is the right way round: these tests judge
whether a model answers correctly, and neither answer is available while the
server is busy.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_URL = "http://localhost:11434"

# Two deadlines, because the two cases cost wildly different amounts. A model
# already resident in VRAM answers a one-token request in about a second on an
# idle server, so anything past WARM_DEADLINE means the server is busy and we
# can stop waiting. A model that is not resident has to be read off disk first
# — 23GB, for the one this project runs — and COLD_DEADLINE covers that.
#
# Splitting them matters during a generation campaign: the model is resident
# and busy for hours, which is exactly the case that now costs seconds instead
# of a minute, every time anyone runs this suite.
WARM_DEADLINE = 10.0
COLD_DEADLINE = 60.0


def endpoint() -> str:
    return os.environ.get("AUTON_OLLAMA_URL", DEFAULT_URL)


def _resident(tag: str) -> bool:
    """Is ``tag`` loaded right now? False on any doubt, including a failure.

    Only ever widens the deadline, so a wrong answer costs waiting, never a
    false skip.
    """
    try:
        with urllib.request.urlopen(f"{endpoint()}/api/ps", timeout=2) as resp:
            payload = json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return False
    return any(m.get("model") == tag or m.get("name") == tag
               for m in payload.get("models", []))


def deadline(tag: str | None = None) -> float:
    override = os.environ.get("AUTON_OLLAMA_PROBE_TIMEOUT")
    if override:
        return float(override)
    if tag is not None and _resident(tag):
        return WARM_DEADLINE
    return COLD_DEADLINE


def _ollama_tag(model: str) -> str:
    """The bare tag Ollama's own API wants, from a LiteLLM model string.

    Callers hold "ollama_chat/qwen3.5:27b" because that is what the resolver
    and the brain are configured with; /api/generate wants "qwen3.5:27b". A
    probe that sent the prefixed name would 404 and report every server as
    busy, which is a guard that always skips — silently useless.
    """
    for prefix in ("ollama_chat/", "ollama/"):
        if model.startswith(prefix):
            return model[len(prefix):]
    return model


def responsive_endpoint(model: str) -> str | None:
    """The base URL if ``model`` produces a token within the deadline, else None.

    None means "cannot judge the model right now" -- unreachable, not installed,
    or busy. Callers skip on it; none of those are a model being wrong.
    """
    url = endpoint()
    tag = _ollama_tag(model)
    body = json.dumps(
        {
            "model": tag,
            "prompt": "hi",
            "stream": False,
            "options": {"num_predict": 1},
        }
    ).encode()
    request = urllib.request.Request(
        f"{url}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=deadline(tag)) as resp:
            if resp.status != 200:
                return None
            json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None
    return url


def skip_reason(model: str) -> str:
    tag = _ollama_tag(model)
    return (
        f"ollama at {endpoint()} did not produce a token from {tag} within "
        f"{deadline(tag):.0f}s: unreachable, not installed, or busy serving "
        f"another request"
    )


def configured_model() -> str | None:
    """The model the brain would use, or None when nothing is configured.

    resolve_model() raises BrainUnavailable when agent/config/auton.toml is
    missing, and that file is local configuration — .gitignore tracks only
    auton.toml.example — so it is absent in every CI checkout. A host with no
    configured model cannot judge a model, which is a skip; calling
    resolve_model() unguarded turns it into a failure instead.
    """
    try:
        from controlplane.operator.brain import BrainUnavailable, resolve_model
    except ImportError:
        return None
    try:
        return resolve_model()
    except BrainUnavailable:
        return None


def live_target() -> tuple[str, str] | None:
    """``(base_url, model)`` when a live model can be judged right now, else None.

    None covers every "not now" — no configured model, unreachable server, or
    one too busy to produce a token. skip_reason() says which.
    """
    model = configured_model()
    if model is None:
        return None
    url = responsive_endpoint(model)
    if url is None:
        return None
    return url, model


def live_skip_reason() -> str:
    model = configured_model()
    if model is None:
        return (
            "no model configured: agent/config/auton.toml is absent (only "
            "auton.toml.example is tracked), so there is nothing to judge"
        )
    return skip_reason(model)
