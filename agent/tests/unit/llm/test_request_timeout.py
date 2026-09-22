"""A model call that never answers must end, and say so.

w12's second live run sat 17 minutes on an Ollama connection with nothing in
flight at the server: an HTTP read with no timeout never returns.
"""

from __future__ import annotations

import asyncio

import pytest

from orchestrator.llm import client as client_module
from orchestrator.llm.client import LLMClient, ModelTimeoutError


async def test_a_hung_call_raises_a_named_timeout(monkeypatch):
    seen = {}

    async def never(**kwargs):
        seen.update(kwargs)
        await asyncio.sleep(3600)

    monkeypatch.setattr(client_module.litellm, "acompletion", never)
    c = LLMClient(model="anthropic/x", preflight=False, request_timeout=0.05)
    monkeypatch.setattr(client_module, "TIMEOUT_BACKSTOP_MARGIN", 0.05)

    with pytest.raises(ModelTimeoutError, match="did not answer dev-01"):
        await c._complete({"model": "anthropic/x", "messages": []}, "dev-01")
    assert seen["timeout"] == 0.05, "the provider is also told the timeout"


def test_the_engine_reads_the_timeout_from_config(tmp_path):
    from orchestrator.core.engine import OrchestrationEngine

    eng = OrchestrationEngine(workspace_path=tmp_path, kernel_spec_path=tmp_path,
                              config={"llm": {"model": "anthropic/x", "request_timeout": 42}})
    assert eng.client.request_timeout == 42.0
