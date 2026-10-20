"""The run event log: one JSON line per model call, tool call, task and review (observability).

It observes; it must never change what a run does, so every failure to write is swallowed.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from orchestrator.core import events
from orchestrator.llm.client import LLMClient


def _lines(path):
    return [json.loads(x) for x in path.read_text().splitlines()]


def test_without_a_destination_emit_does_nothing(monkeypatch):
    monkeypatch.delenv("AUTON_EVENTS", raising=False)
    events.emit("task_start", task="t1")      # no error, no file


def test_emit_appends_one_json_line_with_a_timestamp(monkeypatch, tmp_path):
    dest = tmp_path / "events.jsonl"
    monkeypatch.setenv("AUTON_EVENTS", str(dest))
    events.emit("task_start", task="t1", agent="dev-01")
    events.emit("merge", task="t1", ok=True)
    rows = _lines(dest)
    assert [r["kind"] for r in rows] == ["task_start", "merge"]
    assert rows[0]["task"] == "t1" and rows[0]["agent"] == "dev-01" and rows[0]["t"].endswith("Z")


def test_long_text_is_cut_not_dropped(monkeypatch, tmp_path):
    dest = tmp_path / "events.jsonl"
    monkeypatch.setenv("AUTON_EVENTS", str(dest))
    events.emit("review", summary="x" * 50_000)
    row = _lines(dest)[0]
    assert len(row["summary"]) < 5_000 and row["summary_chars"] == 50_000


def test_an_unwritable_destination_never_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTON_EVENTS", str(tmp_path / "no" / "such" / "dir" / "e.jsonl"))
    events.emit("task_start", task="t1")


def test_a_model_call_and_its_tool_call_are_recorded(monkeypatch, tmp_path):
    dest = tmp_path / "events.jsonl"
    monkeypatch.setenv("AUTON_EVENTS", str(dest))
    call = SimpleNamespace(id="c1", function=SimpleNamespace(name="read_file", arguments='{"path": "a.c"}'))
    msg = SimpleNamespace(content="", tool_calls=[call])
    resp = SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="tool_calls")],
                           usage=SimpleNamespace(prompt_tokens=1200, completion_tokens=80))
    answers = [resp, SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content="done", tool_calls=None), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=1400, completion_tokens=5))]

    async def fake_complete(self, kwargs, agent_id, timeout):
        return answers.pop(0)

    async def executor(name, args):
        return "int main(void) {}"

    client = LLMClient(model="ollama_chat/qwen3-coder:30b", preflight=False, context_length=32768)
    client._complete = fake_complete.__get__(client)
    asyncio.run(client.send_with_tools("dev-01", "s", [{"role": "user", "content": "x"}], [{}], executor))

    rows = _lines(dest)
    kinds = [r["kind"] for r in rows]
    assert kinds == ["llm_call", "tool_call", "llm_call"]
    first = rows[0]
    assert first["agent"] == "dev-01" and first["prompt_tokens"] == 1200
    assert first["completion_tokens"] == 80 and first["finish_reason"] == "tool_calls"
    assert first["tool_calls"] == ["read_file"] and first["seconds"] >= 0
    tool = rows[1]
    assert tool["name"] == "read_file" and tool["result_chars"] == 17 and tool["seconds"] >= 0
    assert len(tool["result"]) <= 130            # a one-line summary, never the whole body


def test_a_failed_model_call_is_recorded_and_still_raises(monkeypatch, tmp_path):
    dest = tmp_path / "events.jsonl"
    monkeypatch.setenv("AUTON_EVENTS", str(dest))

    async def fake_complete(self, kwargs, agent_id, timeout):
        raise RuntimeError("boom")

    client = LLMClient(model="ollama_chat/qwen3-coder:30b", preflight=False)
    client._complete = fake_complete.__get__(client)
    try:
        asyncio.run(client.send_message("a", "s", [{"role": "user", "content": "x"}]))
        raised = False
    except RuntimeError:
        raised = True
    assert raised
    row = _lines(dest)[0]
    assert row["kind"] == "llm_error" and "boom" in row["error"]
