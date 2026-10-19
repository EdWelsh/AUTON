"""`[llm] think = false` reaches the model as reasoning_effort="none" (litellm: think=false)."""

from __future__ import annotations

import asyncio

from orchestrator.llm.client import LLMClient


def _captured(think):
    seen = {}

    async def fake_complete(self, kwargs, agent_id, timeout):
        seen.update(kwargs)
        raise RuntimeError("stop")

    client = LLMClient(model="ollama_chat/qwen3.6:35b-a3b", preflight=False, think=think,
                       context_length=1000)
    client._complete = fake_complete.__get__(client)
    try:
        asyncio.run(client.send_message(agent_id="a", system="s", messages=[{"role": "user", "content": "x"}]))
    except Exception:
        pass
    return seen


def test_think_false_is_passed_to_ollama():
    assert _captured(False).get("reasoning_effort") == "none"


def test_default_leaves_thinking_alone():
    assert "reasoning_effort" not in _captured(None)
