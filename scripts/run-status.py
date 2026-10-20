#!/usr/bin/env python3
"""What a run is doing, and what it did, from its events.jsonl.

    .venv/bin/python scripts/run-status.py .artifacts/campaign/r1-mm-attempt2
    .venv/bin/python scripts/run-status.py <run dir> --json

Reads <run dir>/events.jsonl (written by the orchestrator when generation_run.py starts it).
Prints: the clock (time since the last event, so a stall is visible), the task in flight,
each agent's calls, tokens and speed, slow tools, and every task's rounds and outcome.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SLOW_TOOL_SECONDS = 60


def parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def load(run_dir: Path) -> list[dict]:
    path = run_dir / "events.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue      # a line cut by a kill mid-write
    return rows


def summarise(rows: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    agents: dict[str, dict] = defaultdict(lambda: {"calls": 0, "prompt_tokens": 0,
                                                    "completion_tokens": 0, "model_seconds": 0.0,
                                                    "errors": 0, "tool_calls": 0})
    tasks: dict[str, dict] = {}
    slow, current = [], None
    for r in rows:
        k = r["kind"]
        if k == "llm_call":
            a = agents[r["agent"]]
            a["calls"] += 1
            a["prompt_tokens"] += r.get("prompt_tokens", 0)
            a["completion_tokens"] += r.get("completion_tokens", 0)
            a["model_seconds"] += r.get("seconds", 0)
        elif k == "llm_error":
            agents[r["agent"]]["errors"] += 1
        elif k == "tool_call":
            agents[r["agent"]]["tool_calls"] += 1
            if r.get("seconds", 0) >= SLOW_TOOL_SECONDS:
                slow.append({"t": r["t"], "agent": r["agent"], "name": r["name"],
                             "seconds": r["seconds"]})
        elif k == "task_start":
            t = tasks.setdefault(r["task"], {"title": r.get("title", ""), "starts": 0,
                                             "reviews": [], "state": "running"})
            t["starts"] += 1
            t["state"] = "running"
            current = {"task": r["task"], "agent": r.get("agent"), "since": r["t"]}
        elif k == "task_result":
            t = tasks.setdefault(r["task"], {"title": "", "starts": 0, "reviews": [], "state": ""})
            t["state"] = "built" if r.get("success") else "failed"
            current = None
        elif k == "review":
            t = tasks.setdefault(r["task"], {"title": "", "starts": 0, "reviews": [], "state": ""})
            t["reviews"].append({"by": r.get("by"), "verdict": r.get("verdict")})
            t["state"] = "approved" if r.get("verdict") == "approve" else "rejected"
        elif k == "merge":
            tasks.setdefault(r["task"], {"title": "", "starts": 0, "reviews": [], "state": ""})
            tasks[r["task"]]["state"] = "merged" if r.get("ok") else "merge conflict"
    for a in agents.values():
        a["completion_tokens_per_second"] = (round(a["completion_tokens"] / a["model_seconds"], 1)
                                             if a["model_seconds"] else 0.0)
        a["model_seconds"] = round(a["model_seconds"], 1)
    last = parse(rows[-1]["t"]) if rows else None
    return {"events": len(rows),
            "started": rows[0]["t"] if rows else None,
            "seconds_since_last_event": round((now - last).total_seconds()) if last else None,
            "current": current, "agents": dict(agents), "tasks": tasks, "slow_tools": slow}


def render(s: dict) -> str:
    if not s["events"]:
        return "no events yet (events.jsonl absent or empty)"
    out = [f"{s['events']} events since {s['started']}; last one {s['seconds_since_last_event']} s ago"]
    cur = s["current"]
    out.append(f"in flight: {cur['task']} ({cur['agent']}) since {cur['since']}" if cur
               else "in flight: nothing recorded")
    out.append("\nagent          calls  prompt_tok  out_tok  model_s  out_tok/s  tools  errors")
    for name, a in sorted(s["agents"].items()):
        out.append(f"{name:14} {a['calls']:5} {a['prompt_tokens']:11} {a['completion_tokens']:8} "
                   f"{a['model_seconds']:8} {a['completion_tokens_per_second']:10} "
                   f"{a['tool_calls']:6} {a['errors']:7}")
    out.append("\ntask        state           starts  reviews")
    for tid, t in s["tasks"].items():
        verdicts = ",".join(f"{x['verdict']}" for x in t["reviews"]) or "-"
        out.append(f"{tid:11} {t['state']:15} {t['starts']:6}  {verdicts}   {t['title'][:40]}")
    if s["slow_tools"]:
        out.append(f"\ntools over {SLOW_TOOL_SECONDS} s:")
        out += [f"  {x['t']} {x['agent']} {x['name']} {x['seconds']} s" for x in s["slow_tools"][-8:]]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    s = summarise(load(args.run_dir))
    print(json.dumps(s, indent=1) if args.json else render(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
