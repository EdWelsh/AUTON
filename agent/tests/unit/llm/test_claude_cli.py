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
