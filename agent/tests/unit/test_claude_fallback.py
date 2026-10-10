"""A reached Claude usage limit moves calls to the local model, then back (w23)."""

from __future__ import annotations

import time

import pytest

from orchestrator.llm import claude_cli
from orchestrator.llm.client import LLMClient
from orchestrator.llm.response import LLMResponse

PRIMARY = "claude-cli/claude-sonnet-5-5"
LOCAL = "ollama_chat/qwen3.5:27b-coding-mxfp8"


class Calls:
    def __init__(self, limited=True, wait=3600):
        self.claude = 0
        self.local = []
        self.limited, self.wait = limited, wait

    async def claude_complete(self, model, system, messages, tools, timeout, agent_id="",
                              raise_on_limit=False):
        self.claude += 1
        if self.limited:
            assert raise_on_limit, "must raise, not wait for hours"
            raise claude_cli.UsageLimit(self.wait, "usage limit reached")
        return LLMResponse(text="from claude", model=model)

    async def litellm(self, **kw):
        self.local.append(kw)
        msg = type("M", (), {"content": "from local", "tool_calls": None})()
        return type("R", (), {"choices": [type("C", (), {"message": msg, "finish_reason": "stop"})()],
                              "usage": None, "model": kw["model"]})()


@pytest.fixture
def wired(monkeypatch):
    calls = Calls()
    monkeypatch.setattr(claude_cli, "complete", calls.claude_complete)
    client = LLMClient(model=PRIMARY, preflight=False, fallback_model=LOCAL, fallback_context=4096)
    monkeypatch.setattr(client, "_complete", lambda kwargs, agent_id, timeout=None: calls.litellm(**kwargs))
    return client, calls


async def test_a_reached_limit_moves_the_call_to_the_local_model(wired):
    client, calls = wired
    await client.send_message("a", "sys", [{"role": "user", "content": "hi"}])
    assert calls.claude == 1 and calls.local[0]["model"] == LOCAL
    assert calls.local[0]["num_ctx"] == 4096, "the fallback's own window, not the campaign's"


async def test_while_blocked_claude_is_not_asked_again(wired):
    client, calls = wired
    for _ in range(3):
        await client.send_message("a", "sys", [{"role": "user", "content": "hi"}])
    assert calls.claude == 1 and len(calls.local) == 3


async def test_after_the_reset_claude_is_used_again(wired):
    client, calls = wired
    await client.send_message("a", "sys", [{"role": "user", "content": "hi"}])
    calls.limited = False
    client._claude_blocked_until = time.time() - 1
    out = await client.send_message("a", "sys", [{"role": "user", "content": "hi"}])
    assert out.text == "from claude" and calls.claude == 2


async def test_without_a_fallback_the_old_waiting_path_is_used(monkeypatch):
    seen = {}

    async def fake(model, system, messages, tools, timeout, agent_id="", raise_on_limit=False):
        seen["raise_on_limit"] = raise_on_limit
        return LLMResponse(text="ok", model=model)
    monkeypatch.setattr(claude_cli, "complete", fake)
    client = LLMClient(model=PRIMARY, preflight=False)
    await client.send_message("a", "s", [{"role": "user", "content": "x"}])
    assert seen["raise_on_limit"] is False


def test_the_local_fallback_is_given_longer_than_a_cloud_call():
    from orchestrator.llm.client import FALLBACK_REQUEST_TIMEOUT
    assert FALLBACK_REQUEST_TIMEOUT > 1800, "R5 and R7 lost tasks to 1800 s local calls"
