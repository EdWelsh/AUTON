#!/usr/bin/env python3
"""One generation run of the campaign, unattended: sessions, then gates.

    .venv/bin/python scripts/generation_run.py --run r1-mm --goal goal.txt \
        --model ollama_chat/qwen3.5:27b-coding-mxfp8 --sessions 4 \
        --gate tests/kernel/run_mm_test.sh --gate tests/kernel/run_vmm_test.sh

The Generation Experiment Protocol (docs/GENERATION-QUEUE.md), as a program:

1. A fresh kernel base (`scripts/kernel-base.sh --git`) is the workspace,
   unless the run directory already has one (then this is a resume of it).
2. Session 1 starts the goal; each later session is `--resume`, until the
   run reaches a terminal phase or the session budget is spent. A session
   ends PAUSED at its wall-clock budget with its work committed (w17).
3. The gates run in their pre-registered order, every one, whatever the
   earlier ones said, each with KERNEL_TREE=<workspace>: exit 0 pass,
   1 generated wrong, 2 not generated. Nothing is merged into "failed".
4. Everything is archived in the run directory: config, goal, the pinned
   wrapper, each session's transcript and timing, each gate's output,
   and RESULT.json.

The wrapper is a pinned copy (bash reads a script as it runs; an edit to the
repo's copy mid-run broke w18 live run 3).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def config(template: Path, out: Path, model: str, ws: Path, iterations: int,
           request_timeout: int, context: int) -> Path:
    lines = []
    for line in template.read_text().splitlines():
        if line.startswith("model ="):
            line = f'model = "{model}"'
        elif line.startswith("path ="):
            line = f'path = "{ws}"'
        elif line.startswith("max_iterations ="):
            line = f"max_iterations = {iterations}"
        elif line.startswith("request_timeout ="):
            line = f"request_timeout = {float(request_timeout)}\ncontext_length = {context}"
        lines.append(line)
    cfg = out / "auton.toml"
    cfg.write_text("\n".join(lines) + "\n")
    return cfg


def pinned_wrapper(out: Path) -> Path:
    dst = out / "orchestrate-native.sh"
    if not dst.exists():
        text = (ROOT / "scripts/orchestrate-native.sh").read_text()
        dst.write_text(text.replace('ROOT="$(cd "$(dirname "$0")/.." && pwd)"',
                                    f'ROOT="{ROOT}"', 1))
    return dst


def run_session(n: int, out: Path, wrapper: Path, cfg: Path, goal: str, resume: bool,
                seconds: int) -> dict:
    log = out / f"session-{n}.log"
    env = {**os.environ, "ORCH_TIMEOUT": str(seconds), "ORCH_CONFIG": str(cfg),
           "ORCH_LOG": str(out / f"transcript-{n}.log")}
    args = ["bash", str(wrapper)] + (["--resume"] if resume else [goal])
    started, t0 = now(), time.monotonic()
    r = subprocess.run(args, env=env, capture_output=True, text=True)
    log.write_text(r.stdout + r.stderr)
    tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
    return {"session": n, "resume": resume, "started": started, "finished": now(),
            "seconds": round(time.monotonic() - t0), "rc": r.returncode, "tail": tail}


def run_gate(cmd: str, ws: Path, out: Path, n: int) -> dict:
    env = {**os.environ, "KERNEL_TREE": str(ws)}
    t0 = time.monotonic()
    r = subprocess.run(["bash", "-c", cmd], cwd=ROOT, env=env, capture_output=True, text=True,
                       timeout=3600)
    (out / f"gate-{n}.log").write_text(r.stdout + r.stderr)
    meaning = {0: "pass", 1: "generated wrong", 2: "not generated"}.get(r.returncode,
                                                                         f"exit {r.returncode}")
    return {"gate": cmd, "rc": r.returncode, "meaning": meaning,
            "seconds": round(time.monotonic() - t0),
            "tail": (r.stdout + r.stderr).strip().splitlines()[-4:]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, help="a short name, e.g. r1-mm")
    ap.add_argument("--goal", required=True, help="the pre-registered goal text file")
    ap.add_argument("--model", required=True)
    ap.add_argument("--gate", action="append", default=[],
                    help="a gate command, run from the repo root with KERNEL_TREE set; repeat, in order")
    ap.add_argument("--sessions", type=int, default=4)
    ap.add_argument("--session-seconds", type=int, default=18000)
    ap.add_argument("--iterations", type=int, default=30)
    ap.add_argument("--request-timeout", type=int, default=1800)
    ap.add_argument("--context", type=int, default=32768,
                    help="the local model's context window (Ollama num_ctx); its default can exhaust memory")
    ap.add_argument("--base-rev", default="kernel-base-v5")
    ap.add_argument("--out", help="default: .artifacts/authorship/<date>-<run>")
    ap.add_argument("--gates-only", action="store_true", help="re-run the gates on an existing run")
    args = ap.parse_args(argv)

    out = Path(args.out or ROOT / ".artifacts/authorship" /
               f"{datetime.now(timezone.utc):%Y-%m-%d}-{args.run}").resolve()
    out.mkdir(parents=True, exist_ok=True)
    ws = out / "ws"
    goal = Path(args.goal).read_text().strip()
    (out / "goal.txt").write_text(goal + "\n")
    result_path = out / "RESULT.json"
    result = json.loads(result_path.read_text()) if result_path.exists() else {
        "run": args.run, "model": args.model, "base": args.base_rev, "sessions": [],
        "commit": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                 capture_output=True, text=True).stdout.strip()}

    if not args.gates_only:
        if not ws.exists():
            subprocess.run(["bash", str(ROOT / "scripts/kernel-base.sh"), str(ws), "--git",
                            "--rev", args.base_rev], check=True, capture_output=True)
        cfg = config(ROOT / "agent/config/auton.toml", out, args.model, ws, args.iterations,
                     args.request_timeout, args.context)
        wrapper = pinned_wrapper(out)
        done = len(result["sessions"])
        for n in range(done + 1, args.sessions + 1):
            resume = n > 1 or (ws / ".auton/state.json").exists()
            s = run_session(n, out, wrapper, cfg, goal, resume, args.session_seconds)
            result["sessions"].append(s)
            result_path.write_text(json.dumps(result, indent=2) + "\n")
            print(f"session {n}: rc {s['rc']} after {s['seconds']}s — {' | '.join(s['tail'])}",
                  flush=True)
            if s["rc"] != 75 and s["rc"] != 1:
                break              # terminal (0) or refused (2): no further session helps

    result["gates"] = [run_gate(cmd, ws, out, i) for i, cmd in enumerate(args.gate, 1)]
    result["finished"] = now()
    result_path.write_text(json.dumps(result, indent=2) + "\n")
    for g in result["gates"]:
        print(f"gate: {g['gate']} -> {g['rc']} ({g['meaning']})", flush=True)
    return 0 if result["gates"] and all(g["rc"] == 0 for g in result["gates"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
