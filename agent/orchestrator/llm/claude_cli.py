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

PROTOCOL = """

## How you act (this replaces native tool calling)

You are the model inside an agent loop. You do not run tools yourself. Each reply is ONE JSON
object and nothing else — no prose around it, no code fences:

- To use tools: {"tool_calls": [{"name": "<tool>", "arguments": {...}}]}
  One or more calls; results come back in the next message, in order.
- When the task is finished: {"final": "<your summary or answer>"}

Use only the tools listed below, with arguments matching their schemas.

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


def parse(result: str, model: str) -> LLMResponse:
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
        return LLMResponse(text=str(obj["final"]), model=model)
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
    for attempt in range(MAX_LIMIT_WAITS + 1):
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
            wait = _limit_reset(result)
            if wait is not None and attempt < MAX_LIMIT_WAITS:
                logger.warning("[%s] subscription usage limit; waiting %.0f min (%s)",
                               agent_id, wait / 60, result[:120])
                await asyncio.sleep(wait)
                continue
            raise RuntimeError(f"claude -p failed (exit {proc.returncode}): {result[:400]}")
        return parse(result, name)
    raise RuntimeError("claude -p: usage limit did not reset after repeated waits")
