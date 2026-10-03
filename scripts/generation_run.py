#!/usr/bin/env python3
"""One generation run of the campaign, unattended: sessions, then gates.

    .venv/bin/python scripts/generation_run.py --run r1-mm --goal goal.txt \
        --model ollama_chat/qwen3.5:27b-coding-mxfp8 --sessions 4 \
        --gate tests/kernel/run_mm_test.sh --gate tests/kernel/run_vmm_test.sh

The Generation Experiment Protocol (docs/GENERATION-QUEUE.md), as a program:

1. A fresh kernel base (`scripts/kernel-base.sh --git`) is the workspace,
   unless the run directory already has one (then this is a resume of it).
2. Session 1 starts the goal; each later session is `--resume`, until the
   run reaches a terminal phase or the work budget is spent. A session
   ends PAUSED at its wall-clock budget with its work committed (w17).
   The budget is *work*: sessions x session-seconds, less the time each
   session spent waiting on the model provider's usage limits (amended
   2026-10-03: R1 on the owner's subscription spent 6.25 h of 6.7 waiting).
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
import re
import subprocess
import threading
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


def memory_free() -> int | None:
    """System-wide free memory percent (macOS memory_pressure), or None."""
    try:
        r = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in r.stdout.splitlines():
        if "free percentage" in line:
            return int(line.rsplit(":", 1)[1].strip().rstrip("%"))
    return None


class MemoryGuard(threading.Thread):
    """Pause the run before the host is out of memory.

    A session killed by the system loses its work in flight; one paused by
    SIGTERM commits it and resumes (w17). w18 R1's first session was killed
    by memory pressure; this pauses it first, below `floor` percent free."""

    def __init__(self, cfg: Path, floor: int):
        super().__init__(daemon=True)
        self.cfg, self.floor, self.fired, self._stop = cfg, floor, False, threading.Event()

    def run(self) -> None:
        while not self._stop.wait(30):
            free = memory_free()
            if free is not None and free < self.floor:
                self.fired = True
                subprocess.run(["pkill", "-TERM", "-f", f"orchestrator.cli --config {self.cfg}"])
                return

    def stop(self) -> None:
        self._stop.set()


# claude_cli logs "subscription usage limit; waiting N min" before each wait.
LIMIT_WAIT = re.compile(r"waiting (\d+) min")
MIN_SESSION_SECONDS = 600       # less work budget than this left: not worth a session
MAX_SESSIONS_FACTOR = 6         # a provider that never lets work happen still ends


def limit_wait_seconds(out: Path, n: int, seconds: int) -> int:
    """Seconds session ``n`` spent waiting on usage limits, from its transcript."""
    log = out / f"transcript-{n}.log"
    if not log.exists():
        return 0
    waited = sum(int(m) * 60 for m in LIMIT_WAIT.findall(log.read_text(errors="replace")))
    return min(waited, seconds)


def work_seconds(s: dict) -> int:
    """A session's work: its wall clock less its waits; a memory pause is none."""
    if s.get("memory_paused"):
        return 0
    return max(0, s["seconds"] - s.get("limit_wait_seconds", 0))


def run_session(n: int, out: Path, wrapper: Path, cfg: Path, goal: str, resume: bool,
                seconds: int, floor: int) -> dict:
    log = out / f"session-{n}.log"
    env = {**os.environ, "ORCH_TIMEOUT": str(seconds), "ORCH_CONFIG": str(cfg),
           "ORCH_LOG": str(out / f"transcript-{n}.log")}
    args = ["bash", str(wrapper)] + (["--resume"] if resume else [goal])
    started, t0 = now(), time.monotonic()
    guard = MemoryGuard(cfg, floor)
    guard.start()
    r = subprocess.run(args, env=env, capture_output=True, text=True)
    guard.stop()
    log.write_text(r.stdout + r.stderr)
    tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
    elapsed = round(time.monotonic() - t0)
    return {"session": n, "resume": resume, "started": started, "finished": now(),
            "seconds": elapsed, "rc": r.returncode, "tail": tail,
            "memory_paused": guard.fired,
            "limit_wait_seconds": limit_wait_seconds(out, n, elapsed)}


def make_base(ws: Path, rev: str, tree: str | None, seeds: list[str]) -> None:
    """The workspace a run starts from: a kernel-base tag, or an earlier run's
    resulting tree (its main), plus seeded files, committed as the base."""
    import shutil
    if tree:
        subprocess.run(["git", "clone", "-q", "--branch", "main", "--no-hardlinks", str(tree),
                        str(ws)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(ws), "remote", "remove", "origin"], capture_output=True)
    else:
        subprocess.run(["bash", str(ROOT / "scripts/kernel-base.sh"), str(ws), "--git",
                        "--rev", rev], check=True, capture_output=True)
    if not seeds:
        return
    for spec in seeds:
        dest, _, src = spec.partition("=")
        src_path, dst_path = (ROOT / src).resolve(), ws / dest
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        if src_path.is_dir():
            shutil.copytree(src_path, dst_path, ignore=shutil.ignore_patterns(".git"),
                            dirs_exist_ok=True)
        else:
            shutil.copy2(src_path, dst_path)
    git = ["git", "-C", str(ws), "-c", "user.email=auton@local", "-c", "user.name=AUTON base"]
    subprocess.run(git + ["add", "-A", "-f", "--", *[s.partition("=")[0] for s in seeds]],
                   check=True, capture_output=True)
    subprocess.run(git + ["commit", "-q", "-m", "seed: " + ", ".join(
        s.partition("=")[0] for s in seeds)], check=True, capture_output=True)


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
    ap.add_argument("--base-tree", help="start from this tree's main (an earlier run's workspace) "
                                        "instead of a kernel-base tag")
    ap.add_argument("--seed", action="append", default=[], metavar="DEST=SRC",
                    help="copy SRC (file or directory) to DEST in the workspace before session 1")
    ap.add_argument("--out", help="default: .artifacts/authorship/<date>-<run>")
    ap.add_argument("--gates-only", action="store_true", help="re-run the gates on an existing run")
    ap.add_argument("--memory-floor", type=int, default=15,
                    help="pause the run below this percent of free memory, resume when it recovers")
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
            make_base(ws, args.base_rev, args.base_tree, args.seed)
            result["base"] = args.base_tree or args.base_rev
            result["seed"] = args.seed
        cfg = config(ROOT / "agent/config/auton.toml", out, args.model, ws, args.iterations,
                     args.request_timeout, args.context)
        wrapper = pinned_wrapper(out)
        for old in result["sessions"]:      # recorded before waits were measured
            old.setdefault("limit_wait_seconds", limit_wait_seconds(out, old["session"], old["seconds"]))
        budget = args.sessions * args.session_seconds
        guard_pauses = sum(1 for s in result["sessions"] if s.get("memory_paused"))
        while True:
            work = sum(work_seconds(s) for s in result["sessions"])
            remaining = budget - work
            if remaining < MIN_SESSION_SECONDS:
                break
            if len(result["sessions"]) >= args.sessions * MAX_SESSIONS_FACTOR:
                print("session cap reached: the provider's limits left no time for work", flush=True)
                break
            n = len(result["sessions"]) + 1
            resume = n > 1 or (ws / ".auton/state.json").exists()
            s = run_session(n, out, wrapper, cfg, goal, resume,
                            min(args.session_seconds, remaining), args.memory_floor)
            result["sessions"].append(s)
            result_path.write_text(json.dumps(result, indent=2) + "\n")
            print(f"session {n}: rc {s['rc']} after {s['seconds']}s (waited {s['limit_wait_seconds']}s on limits)"
                  f"{' (memory guard)' if s['memory_paused'] else ''} — {' | '.join(s['tail'])}",
                  flush=True)
            if s["memory_paused"]:
                # Not the run's budget spent: the host's. Unload the model — it
                # stays resident otherwise, and w18 R1's driver was reaped while
                # waiting beside a 41 GB model — then wait for memory, then go on.
                if args.model.startswith(("ollama/", "ollama_chat/")):
                    subprocess.run(["ollama", "stop", args.model.split("/", 1)[1]],
                                   capture_output=True)
                guard_pauses += 1
                if guard_pauses > 10:
                    print("memory guard fired 10 times; stopping the run", flush=True)
                    break
                while (memory_free() or 100) < 30:
                    time.sleep(60)
                continue
            if s["rc"] != 75 and s["rc"] != 1:
                break              # terminal (0) or refused (2): no further session helps

    if args.gates_only and result.get("gates"):
        # A re-grade (stop rule 5: a gate defect fixed) keeps what it replaces.
        result["gate_history"] = [*result.get("gate_history", []),
                                  {"finished": result.get("finished"), "gates": result["gates"]}]
    result["work_seconds"] = sum(work_seconds(s) for s in result["sessions"])
    result["limit_wait_seconds"] = sum(s.get("limit_wait_seconds", 0) for s in result["sessions"])
    result["gates"] = [run_gate(cmd, ws, out, i) for i, cmd in enumerate(args.gate, 1)]
    result["finished"] = now()
    result_path.write_text(json.dumps(result, indent=2) + "\n")
    for g in result["gates"]:
        print(f"gate: {g['gate']} -> {g['rc']} ({g['meaning']})", flush=True)
    return 0 if result["gates"] and all(g["rc"] == 0 for g in result["gates"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
