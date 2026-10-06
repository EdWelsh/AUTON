"""A model backend that runs each call through Claude Code headless (`claude -p`).

    [llm] model = "claude-cli/claude-sonnet-5-5"

Uses the owner's Claude subscription rather than an API key (owner's decision,
2026-10-02). Claude Code runs as a *pure model*: every built-in tool disabled
(`--tools ""`), no settings, hooks or MCP servers loaded, no session kept. The
orchestrator keeps its own tool loop, sandbox, gates and review — only the
model behind them changes.

There is no native tool calling on this path, so the conversation is rendered
as a transcript and the model answers with one JSON object:

    {"tool_calls": [{"name": "...", "arguments": {...}}, ...]}   to act
    {"final": "..."}                                            when done

A reply that is not that JSON is returned as plain text, which ends the turn;
the engine's own checks (tool boundaries, record and package gates) still
refuse anything malformed downstream.

A subscription has usage windows. When `claude -p` reports a usage limit, the
call waits for the reset (or a fixed interval) and tries again rather than
failing the run.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import tempfile
import time
from typing import Any

from orchestrator.llm.response import LLMResponse, ToolCall

logger = logging.getLogger(__name__)

PREFIX = "claude-cli/"
LIMIT_WAIT_SECONDS = 15 * 60
MAX_LIMIT_WAITS = 24
MAX_PARSE_RETRIES = 3
MALFORMED_NUDGE = ("\n\n[harness] Your previous reply tried to call a tool but could not be read. "
                   "Reply again with ONE JSON object as text and nothing else: "
                   "{\"tool_calls\": [{\"name\": \"<tool>\", \"arguments\": {...}}]} "
                   "or {\"final\": \"...\"}.")
# Errors that say nothing about the request: the host slept, the network
# dropped, the service was busy. Retried with backoff, never a task failure
# (w18 R2: "Your computer went to sleep mid-response" failed fs-004, blocked
# three tasks behind it and ended a run with 18 of its 20 work hours unspent).
TRANSIENT = ("went to sleep", "overloaded", "connection", "network", "timed out",
             "timeout", "econnreset", "socket", "internal server error", "503", "502",
             "529", "500", "api error: terminated")
MAX_TRANSIENT_RETRIES = 6
TRANSIENT_BACKOFF_SECONDS = (15, 30, 60, 120, 240, 480)


def _transient(result: str) -> bool:
    low = (result or "").lower()
    return any(t in low for t in TRANSIENT)
# Claude Code's own error when the model emits a native tool call in a session
# with no tools (w18 R1 on Sonnet: it failed mm-002 and ended the run).
UNPARSED_CALL = "tool call could not be parsed"
NUDGE = ("\n\n[harness] Your previous reply was a native tool call, which this session cannot "
         "run. Reply again with ONE JSON object as text: {\"tool_calls\": [...]} or {\"final\": ...}.")

PROTOCOL = """

## How you act (this replaces native tool calling)

You are the model inside an agent loop. You do not run tools yourself. Each reply is ONE JSON
object and nothing else — no prose around it, no code fences:

- To use tools: {"tool_calls": [{"name": "<tool>", "arguments": {...}}]}
  One or more calls; results come back in the next message, in order.
- When the task is finished: {"final": "<your summary or answer>"}

Use only the tools listed below, with arguments matching their schemas. You have no native
tools in this session: write every call as the JSON text above, never as a native tool call.
Prose with no tool call ends your turn, so never describe a call: make it.

## Tools
"""


_EMPTY_CWD: str | None = None


def _cwd() -> str:
    """An empty directory to run in, so no CLAUDE.md or project context is loaded."""
    global _EMPTY_CWD
    if _EMPTY_CWD is None:
        _EMPTY_CWD = tempfile.mkdtemp(prefix="auton-claude-cli-")
    return _EMPTY_CWD


def available() -> bool:
    return shutil.which("claude") is not None


def _render_tools(tools: list[dict[str, Any]] | None) -> str:
    if not tools:
        return "(none: reply with {\"final\": ...})"
    out = []
    for t in tools:
        fn = t.get("function", {})
        out.append(f"- {fn.get('name')}: {fn.get('description', '')}\n"
                   f"  parameters: {json.dumps(fn.get('parameters', {}))}")
    return "\n".join(out)


def render(system: str, messages: list[dict[str, Any]],
           tools: list[dict[str, Any]] | None) -> tuple[str, str]:
    """(system prompt, transcript prompt) for one call."""
    sys_prompt = system + PROTOCOL + _render_tools(tools)
    parts = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            continue
        if role == "tool":
            parts.append(f"[tool result {m.get('tool_call_id', '')}]\n{m.get('content', '')}")
        elif role == "assistant":
            calls = m.get("tool_calls") or []
            if calls:
                rendered = [{"name": c["function"]["name"],
                             "arguments": json.loads(c["function"]["arguments"] or "{}")}
                            for c in calls]
                parts.append("[you]\n" + json.dumps({"tool_calls": rendered}))
            elif m.get("content"):
                parts.append("[you]\n" + json.dumps({"final": m["content"]}))
        else:
            parts.append(f"[user]\n{m.get('content', '')}")
    parts.append("[your next reply: ONE JSON object]")
    return sys_prompt, "\n\n".join(parts)


def _first_json_object(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                esc = (ch == "\\" and not esc)
                if ch == '"' and not esc:
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


_INVOKE = re.compile(r'<invoke\s+name="([^"]+)"\s*>(.*?)</invoke>', re.S)
_PARAM = re.compile(r'<parameter\s+name="([^"]+)"\s*>(.*?)</parameter>', re.S)


def _param_value(raw: str) -> Any:
    """A parameter's text: JSON when it is a number, bool, list or object; else the string."""
    stripped = raw.strip()
    if stripped[:1] in "[{" or stripped in ("true", "false", "null") or re.fullmatch(r"-?\d+(\.\d+)?", stripped):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    return raw


def _invoke_calls(text: str) -> list[ToolCall]:
    """Tool calls written in Claude's native <invoke> format.

    Asked for JSON, Claude drifts back to the format it was trained on after a
    few turns (w18 R1 on Sonnet 5.5: three replies of <invoke> blocks were read
    as final answers, and mm-001 failed with no output). Both are accepted.
    """
    stamp = int(time.time() * 1000)
    calls = [ToolCall(id=f"call_{stamp}_{n}", name=name,
                      arguments={k: _param_value(v) for k, v in _PARAM.findall(body)})
             for n, (name, body) in enumerate(_INVOKE.findall(text))]
    if calls:
        return calls
    # A mangled variant (w18 R3): <tool_calls><parameter name="name">tool</parameter>
    # <parameter name="pattern">...</parameter>... — the tool named by a "name"
    # parameter, the rest its arguments. Only a single, complete call is taken.
    params = _PARAM.findall(text)
    names = [v.strip() for k, v in params if k == "name" and v.strip()]
    if len(names) == 1 and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", names[0]):
        args = {k: _param_value(v) for k, v in params if k != "name"}
        return [ToolCall(id=f"call_{stamp}_0", name=names[0], arguments=args)]
    return []


# Signs a reply meant to call a tool. One that does and still parses to no
# call is re-asked, never taken as the final answer (w18 R1, R3: such replies
# ended tasks with "no output" three times running).
_ATTEMPT_MARKERS = ("<invoke", "<tool_calls", "<parameter", '"tool_calls"', "<function_calls")


def attempted_call(text: str) -> bool:
    return any(m in (text or "") for m in _ATTEMPT_MARKERS)


def parse(result: str, model: str) -> LLMResponse:
    invoked = _invoke_calls(result or "")
    if invoked:
        return LLMResponse(text=None, tool_calls=invoked, finish_reason="tool_calls", model=model)
    obj = _first_json_object(result or "")
    if isinstance(obj, dict) and isinstance(obj.get("tool_calls"), list) and obj["tool_calls"]:
        calls = []
        for n, c in enumerate(obj["tool_calls"]):
            if isinstance(c, dict) and c.get("name"):
                args = c.get("arguments") or {}
                calls.append(ToolCall(id=f"call_{int(time.time() * 1000)}_{n}",
                                      name=str(c["name"]),
                                      arguments=args if isinstance(args, dict) else {}))
        if calls:
            return LLMResponse(text=None, tool_calls=calls, finish_reason="tool_calls", model=model)
    if isinstance(obj, dict) and "final" in obj:
        final = obj["final"]
        return LLMResponse(text=final if isinstance(final, str) else json.dumps(final), model=model)
    return LLMResponse(text=result, model=model)


def _limit_reset(result: str) -> float | None:
    """Seconds to wait when the reply is a usage-limit notice, else None."""
    low = (result or "").lower()
    if "limit" not in low or not any(w in low for w in ("usage", "rate", "reached", "exceeded")):
        return None
    m = re.search(r"\|(\d{10})\b", result)
    if m:
        return max(60.0, float(m.group(1)) - time.time() + 60)
    return float(LIMIT_WAIT_SECONDS)


async def complete(model: str, system: str, messages: list[dict[str, Any]],
                   tools: list[dict[str, Any]] | None, timeout: float,
                   agent_id: str = "") -> LLMResponse:
    name = model[len(PREFIX):]
    sys_prompt, prompt = render(system, messages, tools)
    argv = ["claude", "-p", "--output-format", "json", "--model", name, "--tools", "",
            "--system-prompt", sys_prompt, "--no-session-persistence",
            "--setting-sources", "", "--strict-mcp-config"]
    parse_retries = transient_retries = 0
    for attempt in range(MAX_LIMIT_WAITS + MAX_PARSE_RETRIES + MAX_TRANSIENT_RETRIES + 1):
        proc = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, cwd=_cwd())
        try:
            out, err = await asyncio.wait_for(proc.communicate(prompt.encode()), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            proc.kill()
            await proc.wait()
            raise
        text = out.decode("utf-8", "replace")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            raise RuntimeError(f"claude -p returned no JSON (exit {proc.returncode}): "
                               f"{(text or err.decode('utf-8', 'replace'))[:400]}") from None
        result = str(data.get("result", ""))
        if data.get("is_error") or proc.returncode != 0:
            if UNPARSED_CALL in result and parse_retries < MAX_PARSE_RETRIES:
                parse_retries += 1
                logger.warning("[%s] native tool call refused by claude -p; retry %d/%d with a nudge",
                               agent_id, parse_retries, MAX_PARSE_RETRIES)
                prompt = prompt + NUDGE
                continue
            if _transient(result) and _limit_reset(result) is None \
                    and transient_retries < MAX_TRANSIENT_RETRIES:
                delay = TRANSIENT_BACKOFF_SECONDS[transient_retries]
                transient_retries += 1
                logger.warning("[%s] transient API error; retry %d/%d in %ds (%s)", agent_id,
                               transient_retries, MAX_TRANSIENT_RETRIES, delay, result[:120])
                await asyncio.sleep(delay)
                continue
            wait = _limit_reset(result)
            if wait is not None and attempt < MAX_LIMIT_WAITS:
                logger.warning("[%s] subscription usage limit; waiting %.0f min (%s)",
                               agent_id, wait / 60, result[:120])
                await asyncio.sleep(wait)
                continue
            raise RuntimeError(f"claude -p failed (exit {proc.returncode}): {result[:400]}")
        response = parse(result, name)
        if not response.tool_calls and attempted_call(result) and parse_retries < MAX_PARSE_RETRIES:
            parse_retries += 1
            logger.warning("[%s] unparseable tool call; retry %d/%d with a nudge",
                           agent_id, parse_retries, MAX_PARSE_RETRIES)
            prompt = prompt + MALFORMED_NUDGE
            continue
        return response
    raise RuntimeError("claude -p: usage limit did not reset after repeated waits")
