#!/usr/bin/env python3
"""Repair a failed campaign attempt instead of re-running the phase from nothing.

    .venv/bin/python scripts/repair_run.py r2-storage            # the run's last attempt
    .venv/bin/python scripts/repair_run.py r2-storage --dry-run  # print the command only

Starts a generation run on the failed attempt's workspace (--base-tree), with the run's own
goal, gates and model settings from docs/campaign/runs.yaml, and a note of what its gates said.
The engine's repair phase (core/repair.py) then turns any gate still failing into tasks.
Output goes to .artifacts/repair/<run>-repair<k>/, labelled as a repair of an attempt: it is
never recorded as a campaign attempt, and the failed attempt's directory is not touched.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / ".artifacts/campaign"
OUT = ROOT / ".artifacts/repair"


def last_attempt(name: str) -> Path:
    found = [d for k in (2, 1) if (d := CAMPAIGN / f"{name}-attempt{k}" / "RESULT.json").exists()]
    if not found:
        raise SystemExit(f"{name}: no finished attempt in {CAMPAIGN}")
    return found[0].parent


def gate_note(result: dict) -> str:
    lines = ["A previous attempt at this goal is the tree you start from. It did not pass the "
             "operator's gates. Keep what works; finish and fix only what these gates show.", ""]
    for g in result.get("gates", []):
        if g.get("rc") != 0:
            lines += [f"Gate `{g.get('cmd', '?')}` exit {g['rc']}:", *map(str, g.get("tail", [])), ""]
    return "\n".join(lines)


def build(name: str, attempt: Path, k: int) -> tuple[list[str], Path]:
    spec = yaml.safe_load((ROOT / "docs/campaign/runs.yaml").read_text())
    run = {r["name"]: r for r in spec["runs"]}[name]
    result = json.loads((attempt / "RESULT.json").read_text())
    out = OUT / f"{name}-repair{k}"
    out.mkdir(parents=True, exist_ok=True)
    goal = out / "goal-input.txt"
    goal.write_text((ROOT / "docs/campaign" / run["goal"]).read_text().rstrip()
                    + "\n\n" + gate_note(result))
    cmd = [sys.executable, str(ROOT / "scripts/generation_run.py"), "--run", out.name,
           "--out", str(out), "--goal", str(goal), "--model", spec["model"],
           "--sessions", "1", "--session-seconds", str(spec.get("session_seconds", 18000)),
           "--context", str(spec.get("context", 32768)), "--base-tree", str(attempt / "ws")]
    if spec.get("fallback_model"):
        cmd += ["--fallback-model", spec["fallback_model"]]
    if spec.get("effort"):
        cmd += ["--effort", str(spec["effort"])]
    for g in run["gates"]:
        cmd += ["--gate", g]
    for g in run.get("advisory") or []:
        cmd += ["--advisory", g]
    return cmd, out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    attempt = last_attempt(args.run)
    k = 1
    while (OUT / f"{args.run}-repair{k}" / "RESULT.json").exists():
        k += 1
    cmd, out = build(args.run, attempt, k)
    print(f"repairing {attempt.name} -> {out}")
    if args.dry_run:
        print(" ".join(cmd))
        return 0
    return subprocess.run(cmd, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
