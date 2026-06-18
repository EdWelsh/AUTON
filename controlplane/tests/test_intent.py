"""Tests for the LLM intent layer (Unit 8).

The resolver maps free-form natural language to one of the registry's
capabilities. It uses an LLM when one is configured and reachable, and a
deterministic keyword-overlap fallback otherwise — mirroring the kernel's
neural→rule-engine fallback. These tests exercise the deterministic path
without any network or mocks; the real-LLM path is guarded behind a reachable
endpoint check and skipped when absent.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request

import pytest

from controlplane.core import (
    Capability,
    CapabilityResult,
    CapabilityStatus,
    Registry,
    Router,
)
from controlplane.intent import make_resolver
from controlplane.intent.resolver import deterministic_resolve


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

def _ollama_reachable() -> str | None:
    url = os.environ.get("AUTON_OLLAMA_URL", "http://localhost:11434")
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=1.5) as resp:
            if resp.status == 200:
                return url
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return None


@pytest.mark.asyncio
async def test_real_llm_resolves_intent_if_reachable():
    url = _ollama_reachable()
    if url is None:
        pytest.skip("no reachable ollama endpoint; skipping real-LLM test")

    model = os.environ.get("AUTON_INTENT_MODEL", "ollama/llama3.1:8b")
    reg = _registry()
    resolve = make_resolver(model=model, endpoints={"ollama": url})
    # A phrase with no keyword substring overlap with docker, to force the LLM
    # to do real semantic mapping rather than the fallback.
    cap = resolve("bundle my server so it runs the same everywhere", reg)
    assert cap is not None
    assert cap.name in {c.name for c in reg.unique_by_name()}
