"""The claude-cli backend: the owner's subscription through `claude -p` (2026-10-02)."""

from __future__ import annotations

import json
import time

from orchestrator.llm import claude_cli

TOOLS = [{"type": "function", "function": {"name": "write_file", "description": "write",
          "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}]


def test_a_tool_call_reply_becomes_tool_calls():
    r = claude_cli.parse('{"tool_calls": [{"name": "write_file", "arguments": {"path": "a.h"}}]}', "m")
    assert [(c.name, c.arguments) for c in r.tool_calls] == [("write_file", {"path": "a.h"})]
    assert r.text is None


def test_a_final_reply_is_text():
    assert claude_cli.parse('{"final": "done"}', "m").text == "done"


def test_prose_around_the_json_and_fences_are_tolerated():
    r = claude_cli.parse('Sure.\n```json\n{"tool_calls": [{"name": "write_file", "arguments": {}}]}\n```', "m")
    assert r.tool_calls and r.tool_calls[0].name == "write_file"


def test_braces_inside_strings_do_not_confuse_the_parser():
    r = claude_cli.parse('{"tool_calls": [{"name": "write_file", "arguments": {"content": "int f() { return 1; }"}}]}', "m")
    assert r.tool_calls[0].arguments["content"] == "int f() { return 1; }"


def test_unparseable_text_ends_the_turn_as_text():
    r = claude_cli.parse("I could not decide.", "m")
    assert r.text == "I could not decide." and not r.tool_calls


def test_the_transcript_carries_calls_and_results_in_order():
    msgs = [{"role": "user", "content": "do it"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "write_file", "arguments": json.dumps({"path": "a.h"})}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "Written 3 bytes"}]
    system, prompt = claude_cli.render("You are a developer.", msgs, TOOLS)
    assert "write_file" in system and "ONE JSON" in system
    assert prompt.index("[user]") < prompt.index('"write_file"') < prompt.index("Written 3 bytes")


def test_a_usage_limit_notice_waits_for_its_reset():
    reset = int(time.time()) + 3600
    wait = claude_cli._limit_reset(f"Claude AI usage limit reached|{reset}")
    assert 3600 <= wait <= 3700
    assert claude_cli._limit_reset("All done.") is None


def test_native_invoke_blocks_are_tool_calls():
    """w18 R1 on Sonnet: <invoke> replies were read as final answers; mm-001 failed."""
    reply = ('<invoke name="shell">\n<parameter name="command">git status --short</parameter>\n'
             '<parameter name="timeout">120</parameter>\n</invoke>\n</tool_calls>\n'
             'Correction, I will proceed. <invoke name="edit_file"><parameter name="path">a.h</parameter>'
             '<parameter name="old">/* x */</parameter><parameter name="new">/* y { } */</parameter></invoke>')
    r = claude_cli.parse(reply, "m")
    assert [c.name for c in r.tool_calls] == ["shell", "edit_file"]
    assert r.tool_calls[0].arguments == {"command": "git status --short", "timeout": 120}
    assert r.tool_calls[1].arguments["new"] == "/* y { } */"


def test_invoke_values_keep_strings_that_only_look_like_json():
    r = claude_cli.parse('<invoke name="list_files"><parameter name="path">kernel</parameter>'
                         '<parameter name="recursive">true</parameter></invoke>', "m")
    assert r.tool_calls[0].arguments == {"path": "kernel", "recursive": True}


async def test_a_refused_native_call_is_retried_with_a_nudge(monkeypatch):
    """w18 R1: claude -p's 'tool call could not be parsed' failed mm-002 and ended the run."""
    replies = [{"is_error": True, "result": "The model's tool call could not be parsed (retry also failed)."},
               {"is_error": False, "result": '{"final": "ok"}'}]
    prompts = []

    class Proc:
        returncode = 0

        def __init__(self, reply):
            self.reply = reply
            self.returncode = 1 if reply["is_error"] else 0

        async def communicate(self, data):
            prompts.append(data.decode())
            return json.dumps(self.reply).encode(), b""

    async def spawn(*a, **k):
        return Proc(replies.pop(0))
    monkeypatch.setattr(claude_cli.asyncio, "create_subprocess_exec", spawn)
    r = await claude_cli.complete("claude-cli/m", "sys", [{"role": "user", "content": "go"}], TOOLS, 60)
    assert r.text == "ok" and "[harness]" in prompts[1] and "[harness]" not in prompts[0]


def test_a_structured_final_is_serialised_as_json():
    r = claude_cli.parse('{"final": [{"task_id": "mm-001"}]}', "m")
    assert json.loads(r.text) == [{"task_id": "mm-001"}]


async def test_a_transient_api_error_is_retried_not_a_task_failure(monkeypatch):
    """w18 R2: 'Your computer went to sleep mid-response' failed fs-004 and ended the run."""
    replies = [{"is_error": True, "result": "API Error: Your computer went to sleep mid-response. "
                                            "The response above may be incomplete."},
               {"is_error": False, "result": '{"final": "ok"}'}]

    class Proc:
        def __init__(self, reply):
            self.reply, self.returncode = reply, (1 if reply["is_error"] else 0)

        async def communicate(self, data):
            return json.dumps(self.reply).encode(), b""

    async def spawn(*a, **k):
        return Proc(replies.pop(0))

    async def no_sleep(_):
        return None
    monkeypatch.setattr(claude_cli.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(claude_cli.asyncio, "sleep", no_sleep)
    r = await claude_cli.complete("claude-cli/m", "sys", [{"role": "user", "content": "go"}], TOOLS, 60)
    assert r.text == "ok"


def test_a_usage_limit_is_not_mistaken_for_a_transient_error():
    assert claude_cli._limit_reset("You've hit your usage limit · resets 5pm") is not None
    assert claude_cli._transient("API Error: Your computer went to sleep mid-response")


def test_a_tool_named_by_a_name_parameter_is_a_call():
    """w18 R3: <tool_calls><parameter name="name">search_code</parameter>... ended fs-002."""
    r = claude_cli.parse('<tool_calls> <parameter name="name">search_code</parameter> '
                         '<parameter name="pattern">vfs_mount|fat32</parameter> </parameter> </invoke>', "m")
    assert [(c.name, c.arguments) for c in r.tool_calls] == [("search_code", {"pattern": "vfs_mount|fat32"})]


async def test_an_unparseable_call_is_re_asked_not_final(monkeypatch):
    replies = [{"is_error": False, "result": "<tool_calls> </tool_calls> <invoke> </invoke>"},
               {"is_error": False, "result": '{"final": "ok"}'}]
    prompts = []

    class Proc:
        returncode = 0

        def __init__(self, reply):
            self.reply = reply

        async def communicate(self, data):
            prompts.append(data.decode())
            return json.dumps(self.reply).encode(), b""

    async def spawn(*a, **k):
        return Proc(replies.pop(0))
    monkeypatch.setattr(claude_cli.asyncio, "create_subprocess_exec", spawn)
    r = await claude_cli.complete("claude-cli/m", "sys", [{"role": "user", "content": "go"}], TOOLS, 60)
    assert r.text == "ok" and "could not be read" in prompts[1]


def test_plain_prose_is_still_a_final_answer():
    assert not claude_cli.attempted_call("The task is done; all files are written.")
