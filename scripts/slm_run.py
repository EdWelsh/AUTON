#!/usr/bin/env python3
"""Run the SLM swarm in a testing area: data, config, training, parity, chat eval, export.

    .venv/bin/python scripts/slm_run.py start chat-1 --goal "Train the kernel chat model"
    .venv/bin/python scripts/slm_run.py start chat-1 --resume
    .venv/bin/python scripts/slm_run.py status chat-1

A run lives in .artifacts/slm/<name>/ (gitignored): the swarm's workspace (ws/), a
kernel base tree (kernel/) materialised with scripts/kernel-base.sh for parity and
the chat eval to build and boot, the config and the log. The swarm follows
SLM/DATA.md: corpora generated from ground truth and checked against the kernel
tokenizer's 1,024-word budget, AUTON-format export, parity, then the eval's bar.

It spends model calls (one per agent turn) and CPU time for training: start one.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".artifacts" / "slm"
TEMPLATES = (ROOT / "agent" / "config" / "auton.toml",
             ROOT / "agent" / "config" / "auton.toml.example")
GRACE = 60                  # seconds between SIGTERM (pause) and SIGKILL


def config_template() -> Path:
    """The operator's agent/config/auton.toml (its keys and endpoints), else the example."""
    return next(p for p in TEMPLATES if p.exists())


def run_bounded(cmd: list[str], cwd: Path, log, seconds: int) -> int:
    """Run ``cmd`` for at most ``seconds``, as `timeout -k GRACE` did, without needing it.

    At the limit, or on Ctrl-C, the child's process group gets SIGTERM, which the
    engine takes as "pause": it commits the work in flight. SIGKILL follows after
    GRACE seconds, or at a second Ctrl-C. The child has its own session, so the
    terminal's Ctrl-C reaches it only this way; with `timeout` it did not reach
    it at all, and the run outlived the launcher with no limit."""
    p = subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                         start_new_session=True)
    try:
        return p.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        rc = 124                                    # timeout(1)'s "timed out"
    except KeyboardInterrupt:
        rc = 130
    _signal_group(p, signal.SIGTERM)
    try:
        p.wait(timeout=GRACE)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        _signal_group(p, signal.SIGKILL)
        p.wait()
    return rc


def _signal_group(p: subprocess.Popen, sig: int) -> None:
    try:
        os.killpg(p.pid, sig)
    except ProcessLookupError:
        pass


def patched(template: Path, patches: dict[str, str]) -> str:
    """``template`` with every line that starts with a key replaced by its value.

    Every key must be found: an operator's auton.toml older than the example
    could lack one, and a run that silently kept e.g. kernel_build mode would
    write kernel code where it should train."""
    lines, found = [], set()
    for line in template.read_text().splitlines():
        key = next((k for k in patches if line.startswith(k)), None)
        if key is not None:
            line = patches[key]
            found.add(key)
        lines.append(line)
    if missing := [k for k in patches if k not in found]:
        raise SystemExit(f"{template}: no line starting {', '.join(map(repr, missing))}; "
                         f"add them from auton.toml.example")
    return "\n".join(lines) + "\n"


def config(run: Path, model: str, base: str) -> Path:
    cfg = run / "auton.toml"
    cfg.write_text(patched(config_template(), {
        "model =": f'model = "{model}"',
        "path =": f'path = "{run / "ws"}"',
        "specialists =": "specialists = false",          # an SLM run writes no kernel code
        'mode = "kernel_build"': 'mode = "slm_training"',
        "kernel_tree =": f'kernel_tree = "{run / "kernel"}"',
    }))
    return cfg


def start(args) -> int:
    run = OUT / args.name
    if (run / "ws").exists() and not args.resume:
        print(f"{run} exists; pass --resume to continue it", file=sys.stderr)
        return 2
    run.mkdir(parents=True, exist_ok=True)
    if not (run / "kernel").exists():
        subprocess.run([str(ROOT / "scripts/kernel-base.sh"), str(run / "kernel"),
                        "--rev", args.base], check=True)
    cfg = config(run, args.model, args.base)
    py = os.environ.get("PYTHON") or str(ROOT / ".venv/bin/python")
    cmd = [py, "-m", "orchestrator.cli",
           "--config", str(cfg), "run", "--workspace", str(run / "ws"),
           "--specs", str(ROOT / "agent" / "kernel_spec")]
    cmd += ["--resume"] if args.resume else [args.goal]
    with open(run / "run.log", "a") as log:
        return run_bounded(cmd, ROOT / "agent", log, args.timeout)


def status(args) -> int:
    ws = OUT / args.name / "ws"
    if not ws.is_dir():
        print(f"no run {args.name!r} in {OUT}", file=sys.stderr)
        return 2
    for rel in ("slm/data/os_chat.jsonl", "slm/data/hardware_kernel.jsonl", "slm/work/vocab.json",
                "slm/work/final.pt", "slm/work/auton-slm-fp32.bin", "slm/eval/fp32.json",
                "slm/export/auton-slm.bin"):
        print(f"{'yes' if (ws / rel).exists() else ' - '}  {rel}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("name")
    s.add_argument("--goal")
    s.add_argument("--resume", action="store_true")
    s.add_argument("--model", default="claude-cli/claude-sonnet-5-5")
    s.add_argument("--base", default="kernel-base-v5")
    s.add_argument("--timeout", type=int, default=7200)
    st = sub.add_parser("status")
    st.add_argument("name")
    args = ap.parse_args(argv)
    if args.cmd == "start" and not (args.goal or args.resume):
        ap.error("start needs --goal (or --resume)")
    return start(args) if args.cmd == "start" else status(args)


if __name__ == "__main__":
    raise SystemExit(main())
