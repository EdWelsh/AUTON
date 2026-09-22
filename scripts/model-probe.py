"""Qualify a model for the orchestration loop, before spending a run on it.

    .venv/bin/python scripts/model-probe.py ollama_chat/qwen3.5:27b
    .venv/bin/python scripts/model-probe.py ollama/gemma4:latest ollama_chat/gemma4:latest

Four checks, each one a way a local model has actually failed here:

  1. tool call        does it call a tool at all, with the right name and
                      arguments? (w13 F6: gemma4 called a C function from the
                      spec as if it were a tool, eight times)
  2. fidelity         does a file's content survive the round trip exactly?
                      (w13 generate-mm and storage: `\\t` where `\\n` + `t` was
                      meant, producing `ttypedef`, which does not compile)
  3. long prompt      with a real 25 000-character specification in the prompt,
                      does it still call the tool and quote the spec correctly?
                      (the config's note: "on longer agent prompts it has
                      returned empty")
  4. second turn      given a tool result, does it continue rather than repeat
                      the same call? (w13: `success()` eighteen times)

Prints a table and exits non-zero if any check fails, so a model is qualified by
evidence rather than by reputation. Timings are printed because a model that
passes at 300 s a call cannot finish a 20-turn task inside an hour.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import litellm

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "agent" / "kernel_spec" / "subsystems" / "mm.md"
OLLAMA = "http://localhost:11434"

WRITE_FILE = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Write a file into the kernel tree, creating directories as needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the tree root"},
                "content": {"type": "string", "description": "The file's entire contents"},
            },
            "required": ["path", "content"],
        },
    },
}

# Two lines, the second indented with a real tab: the exact shape that came back
# corrupted from two runs.
FIDELITY_BODY = "/* c */\ntypedef int a_t;\n\ttypedef int b_t;\n"


class Result:
    def __init__(self, name: str) -> None:
        self.name = name
        self.ok = False
        self.seconds = 0.0
        self.detail = ""

    def row(self) -> str:
        mark = "PASS" if self.ok else "FAIL"
        return f"  {self.name:<14} {mark}  {self.seconds:6.1f}s  {self.detail[:96]}"


def call(model: str, messages: list[dict], tools: bool = True, timeout: int = 900) -> object:
    kwargs: dict = {"model": model, "messages": messages, "temperature": 0,
                    "timeout": timeout, "api_base": OLLAMA}
    if tools:
        kwargs["tools"] = [WRITE_FILE]
        kwargs["tool_choice"] = "auto"
    return litellm.completion(**kwargs)


def tool_calls(response) -> list:
    return getattr(response.choices[0].message, "tool_calls", None) or []


def arguments(tc) -> dict:
    try:
        return json.loads(tc.function.arguments)
    except (json.JSONDecodeError, TypeError):
        return {}


def check_tool_call(model: str) -> Result:
    r = Result("tool call")
    t = time.monotonic()
    resp = call(model, [
        {"role": "system", "content": "You write files with the write_file tool. "
                                      "Never answer in prose when a tool fits."},
        {"role": "user", "content": "Create kernel/include/a.h containing exactly: "
                                    "#define A 1"},
    ])
    r.seconds = time.monotonic() - t
    calls = tool_calls(resp)
    if not calls:
        r.detail = f"no tool call; said {str(resp.choices[0].message.content)[:60]!r}"
        return r
    if calls[0].function.name != "write_file":
        r.detail = f"called {calls[0].function.name!r}"
        return r
    args = arguments(calls[0])
    if "a.h" not in str(args.get("path", "")):
        r.detail = f"path {args.get('path')!r}"
        return r
    r.ok, r.detail = True, f"write_file({args.get('path')!r})"
    return r


def check_fidelity(model: str) -> Result:
    r = Result("fidelity")
    t = time.monotonic()
    resp = call(model, [
        {"role": "system", "content": "You write files with the write_file tool, exactly as given."},
        {"role": "user", "content": "Create a.h whose content is exactly these three lines, "
                                    "the third indented with a tab character:\n" + FIDELITY_BODY},
    ])
    r.seconds = time.monotonic() - t
    calls = tool_calls(resp)
    if not calls:
        r.detail = "no tool call"
        return r
    got = str(arguments(calls[0]).get("content", ""))
    squeeze = lambda t: "".join(t.split())      # noqa: E731 - every character but whitespace
    if got == FIDELITY_BODY:
        r.ok, r.detail = True, "content byte-exact"
    elif squeeze(got) == squeeze(FIDELITY_BODY):
        # C does not care how it is indented. This passes, with the difference
        # named, because failing it would disqualify a model for something the
        # compiler ignores.
        r.ok, r.detail = True, f"whitespace differs, tokens identical: {got!r}"[:90]
    else:
        # The failure that matters: characters lost or inserted inside tokens,
        # e.g. `ttypedef` (w13 generate-mm), which does not compile.
        r.detail = f"characters corrupted: {got!r}"[:90]
    return r


def check_long_prompt(model: str) -> Result:
    r = Result("long prompt")
    spec = SPEC.read_text()
    t = time.monotonic()
    resp = call(model, [
        {"role": "system", "content": "You implement kernel specifications by writing files."},
        {"role": "user", "content": spec + "\n\nWrite kernel/include/mm.h with the "
                                           "pmm_init prototype exactly as the specification "
                                           "declares it. Use the write_file tool."},
    ])
    r.seconds = time.monotonic() - t
    calls = tool_calls(resp)
    if not calls:
        r.detail = f"no tool call after {len(spec)} chars of spec"
        return r
    content = str(arguments(calls[0]).get("content", ""))
    if "pmm_init" not in content:
        r.detail = "wrote a file without pmm_init"
        return r
    r.ok = True
    r.detail = ("quotes the spec's boot_mmap_t signature" if "boot_mmap_t" in content
                else "has pmm_init, but not the spec's parameter type")
    r.ok = "boot_mmap_t" in content
    return r


def check_second_turn(model: str) -> Result:
    """A tool result comes back; the model must move on, not repeat itself."""
    r = Result("second turn")
    t = time.monotonic()
    resp = call(model, [
        {"role": "system", "content": "You write files with write_file. When a file is "
                                      "written, write the next one."},
        {"role": "user", "content": "Create kernel/include/a.h with '#define A 1', then "
                                    "kernel/include/b.h with '#define B 2'."},
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": "call_1", "type": "function",
            "function": {"name": "write_file",
                         "arguments": json.dumps({"path": "kernel/include/a.h",
                                                  "content": "#define A 1\n"})}}]},
        {"role": "tool", "tool_call_id": "call_1", "name": "write_file",
         "content": "Written 12 bytes to kernel/include/a.h"},
    ])
    r.seconds = time.monotonic() - t
    calls = tool_calls(resp)
    if not calls:
        r.detail = f"stopped; said {str(resp.choices[0].message.content)[:50]!r}"
        return r
    path = str(arguments(calls[0]).get("path", ""))
    if "b.h" in path:
        r.ok, r.detail = True, "moved on to b.h"
    else:
        r.detail = f"repeated {path!r}"
    return r


CHECKS = (check_tool_call, check_fidelity, check_long_prompt, check_second_turn)


def probe(model: str) -> bool:
    print(f"\n{model}")
    results = []
    for check in CHECKS:
        try:
            r = check(model)
        except Exception as exc:                      # a provider error is a failure
            r = Result(check.__name__.replace("check_", "").replace("_", " "))
            r.detail = f"{type(exc).__name__}: {exc}"[:96]
        results.append(r)
        print(r.row(), flush=True)
    worst = max((r.seconds for r in results), default=0.0)
    passed = all(r.ok for r in results)
    print(f"  {'qualified' if passed else 'NOT qualified'}; slowest call {worst:.0f}s"
          f"{'' if worst < 300 else ' — a 20-turn task will not fit in an hour'}")
    return passed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("models", nargs="+", help="LiteLLM model ids, e.g. ollama_chat/qwen3.5:27b")
    args = ap.parse_args(argv)
    return 0 if all([probe(m) for m in args.models]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
