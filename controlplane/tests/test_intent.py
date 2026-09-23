"""Tests for the LLM intent layer (Unit 8).

The resolver maps free-form natural language to one of the registry's
capabilities. It uses an LLM when one is configured and reachable, and a
deterministic keyword-overlap fallback otherwise — mirroring the kernel's
neural→rule-engine fallback. These tests exercise the deterministic path
without any network or mocks; the real-LLM path is guarded behind a reachable
endpoint check and skipped when absent.
"""

from __future__ import annotations

import asyncio
import gc
import os
import warnings
from types import SimpleNamespace

import pytest
from controlplane.core import (
    Capability,
    CapabilityResult,
    CapabilityStatus,
    Registry,
    Router,
)
from controlplane.intent import make_resolver
from controlplane.intent.resolver import _resolve_via_llm, deterministic_resolve
from tests.ollama_probe import (
    live_skip_reason,
    live_target,
    responsive_endpoint,
    skip_reason,
)


def _docker_cap() -> Capability:
    return Capability(
        name="docker",
        keywords=("docker", "container"),
        status=CapabilityStatus.WORKING,
        note="run and manage docker containers and images",
        handler=lambda text: CapabilityResult.ok("docker handled"),
    )


def _k8s_cap() -> Capability:
    return Capability(
        name="kubernetes",
        keywords=("kubectl", "k8s", "pod"),
        status=CapabilityStatus.WORKING,
        note="deploy and scale kubernetes workloads",
        handler=lambda text: CapabilityResult.ok("k8s handled"),
    )


def _desktop_cap() -> Capability:
    return Capability(
        name="desktop",
        keywords=("open", "launch", "app"),
        status=CapabilityStatus.WORKING,
        note="launch desktop applications and windows",
        handler=lambda text: CapabilityResult.ok("desktop handled"),
    )


def _registry() -> Registry:
    return Registry([_docker_cap(), _k8s_cap(), _desktop_cap()])


# --- 1. Deterministic fallback, no network -------------------------------

def test_fallback_resolves_containerize_to_docker():
    reg = _registry()
    cap = deterministic_resolve("please put this in a container", reg)
    assert cap is not None
    assert cap.name == "docker"


def test_fallback_resolves_kubernetes_phrasing():
    reg = _registry()
    cap = deterministic_resolve("scale the pod deployment", reg)
    assert cap is not None
    assert cap.name == "kubernetes"


def test_fallback_returns_none_for_gibberish():
    reg = _registry()
    assert deterministic_resolve("zxqw flibberty gronk", reg) is None


def test_fallback_returns_none_for_empty_text():
    reg = _registry()
    assert deterministic_resolve("   ", reg) is None


def test_make_resolver_without_llm_uses_fallback():
    """With no LLM configured, the resolver must still work offline."""
    reg = _registry()
    resolve = make_resolver()  # no model/config => deterministic only
    cap = resolve("spin up a container for me", reg)
    assert cap is not None
    assert cap.name == "docker"
    assert resolve("zxqw flibberty gronk", reg) is None


# --- 3. Routing smoke (fallback via Router) ------------------------------

def test_router_uses_resolver_when_no_keyword_match():
    reg = _registry()
    router = Router(reg, intent_resolver=make_resolver())
    # No capability keyword ("docker"/"container"/"pod"/"app"/...) is a substring
    # of this phrase, so registry.match misses and the resolver fallback fires.
    # The deterministic path then picks docker by lexical overlap with the docker
    # note ("run and manage docker containers and images") — "manage"/"images".
    text = "i need to ship and manage images for my service"
    assert reg.match(text) is None
    result = router.route(text)
    assert isinstance(result, CapabilityResult)
    assert result.handled
    assert result.text == "docker handled"


def test_router_resolver_returns_unhandled_for_gibberish():
    reg = _registry()
    router = Router(reg, intent_resolver=make_resolver())
    result = router.route("zxqw flibberty gronk")
    assert not result.handled


# --- 2. Real-LLM path, guarded ------------------------------------------

@pytest.mark.asyncio
async def test_real_llm_resolves_intent_if_reachable():
    # Reachable is not enough: /api/tags answers instantly on a server that is
    # fully occupied, and the call below would then queue for as long as the
    # agent client allows. live_target also refuses when no model is configured.
    # See tests/ollama_probe.py.
    override = os.environ.get("AUTON_INTENT_MODEL")
    if override:
        # An explicit override still has to be answerable, but it does not need
        # the repo's own config to exist.
        url = responsive_endpoint(override)
        if url is None:
            pytest.skip(skip_reason(override))
        model = override
    else:
        # Default to the configured model rather than a second hardcoded name —
        # that divergence is exactly what this test would otherwise stop catching.
        target = live_target()
        if target is None:
            pytest.skip(live_skip_reason())
        url, model = target

    reg = _registry()
    resolve = make_resolver(model=model, endpoints={"ollama": url})
    # A phrase with no keyword substring overlap with docker, to force the LLM
    # to do real semantic mapping rather than the fallback.
    cap = resolve("bundle my server so it runs the same everywhere", reg)
    assert cap is not None
    assert cap.name in {c.name for c in reg.unique_by_name()}


# --- 4. Coroutine lifecycle on the LLM path -----------------------------

class _StubClient:
    """The LLMClient surface the resolver actually uses: one async method.

    Not a stand-in for a model's answers — it is the seam that makes the
    coroutine-lifecycle bug testable deterministically, with no network and no
    dependence on which loop the caller happens to be running.
    """

    def __init__(self, reply: str = "docker", raises: Exception | None = None):
        self.reply = reply
        self.raises = raises
        self.calls = 0

    async def send_message(self, agent_id, system, messages, temperature=0.0):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return SimpleNamespace(text=self.reply)


def _resolve_via_llm_capturing_warnings(client, text: str):
    """Run the LLM resolver path; return (capability, RuntimeWarnings raised).

    "coroutine was never awaited" is emitted by the garbage collector when the
    orphaned coroutine is finalised, not at the call site — so the collection
    has to happen inside the capture block for the warning to be seen at all.
    """
    caps = _registry().unique_by_name()
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        picked = _resolve_via_llm(client, "test-intent", text, caps)
        gc.collect()
    return picked, [w for w in record if issubclass(w.category, RuntimeWarning)]


def test_llm_path_inside_running_loop_leaks_no_coroutine():
    """The regression: asyncio.run() rejects a running loop before awaiting.

    A coroutine built inline as its argument was then discarded unawaited. The
    resolver still has to resolve — via the threaded fallback — and do it
    without leaving a RuntimeWarning behind.
    """
    client = _StubClient(reply="docker")

    async def _inside_loop():
        return _resolve_via_llm_capturing_warnings(client, "put this in a container")

    picked, runtime_warnings = asyncio.run(_inside_loop())

    assert picked is not None and picked.name == "docker"
    assert client.calls == 1, "the threaded fallback must still make the call"
    assert runtime_warnings == [], f"leaked: {[str(w.message) for w in runtime_warnings]}"


def test_llm_path_leaves_no_coroutine_when_the_call_errors():
    """An erroring model degrades to None (the caller's backstop), warning-free."""
    client = _StubClient(raises=ConnectionError("ollama is down"))

    picked, runtime_warnings = _resolve_via_llm_capturing_warnings(client, "spin up a container")

    assert picked is None, "an errored call hands off to the deterministic backstop"
    assert runtime_warnings == [], f"leaked: {[str(w.message) for w in runtime_warnings]}"


def test_llm_path_outside_a_loop_leaves_no_coroutine():
    """The ordinary synchronous path must stay clean too."""
    client = _StubClient(reply="kubernetes")

    picked, runtime_warnings = _resolve_via_llm_capturing_warnings(client, "scale my workload out")

    assert picked is not None and picked.name == "kubernetes"
    assert runtime_warnings == []


def test_erroring_resolver_still_routes_via_the_deterministic_backstop():
    """End of the chain: a dead LLM must not stop the router from resolving."""
    reg = _registry()
    router = Router(reg, intent_resolver=make_resolver(model="ollama/definitely-not-installed"))
    result = router.route("i need to ship and manage images for my service")
    assert result.handled and result.text == "docker handled"
