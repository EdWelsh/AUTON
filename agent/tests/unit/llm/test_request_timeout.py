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


def test_tool_calls_are_logged_without_file_bodies():
    from orchestrator.llm.client import _summarise_args, _summarise_result

    line = _summarise_args({"path": "kernel/a.c", "content": "x" * 5000})
    assert "path='kernel/a.c'" in line and "<5000 chars>" in line and "xxxx" not in line
    assert _summarise_result("y" * 500).endswith("(500 chars)")


class TestTheToolTurnCap:
    """20 turns was never a considered number, and it ended w14's F6 run: the
    model wrote a working TFTP server, then hit the cap with its tests
    unwritten. A model that reads before it writes spends turns on reading."""

    def test_the_cap_defaults_to_twenty(self):
        from orchestrator.llm.client import DEFAULT_MAX_TOOL_TURNS, LLMClient

        client = LLMClient(model="ollama_chat/x", preflight=False)
        assert client.max_tool_turns == DEFAULT_MAX_TOOL_TURNS == 20

    def test_the_cap_is_configurable(self):
        from orchestrator.llm.client import LLMClient

        assert LLMClient(model="ollama_chat/x", preflight=False,
                         max_tool_turns=60).max_tool_turns == 60

    def test_the_engine_reads_it_from_config(self):
        from pathlib import Path

        import orchestrator.core.engine as engine

        text = Path(engine.__file__).read_text()
        assert 'llm_config.get("max_tool_turns"' in text
