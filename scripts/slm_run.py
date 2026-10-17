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
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".artifacts" / "slm"
TEMPLATE = ROOT / "agent" / "config" / "auton.toml.example"


def config(run: Path, model: str, base: str) -> Path:
    lines = []
    for line in TEMPLATE.read_text().splitlines():
        if line.startswith("model ="):
            line = f'model = "{model}"'
        elif line.startswith("path ="):
            line = f'path = "{run / "ws"}"'
        elif line.startswith("specialists ="):
            line = "specialists = false"              # an SLM run writes no kernel code
        elif line.startswith('mode = "kernel_build"'):
            line = 'mode = "slm_training"'
        elif line.startswith("kernel_tree ="):
            line = f'kernel_tree = "{run / "kernel"}"'
        lines.append(line)
    cfg = run / "auton.toml"
    cfg.write_text("\n".join(lines) + "\n")
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
    cmd = ["timeout", "-k", "60", str(args.timeout), py, "-m", "orchestrator.cli",
           "--config", str(cfg), "run", "--workspace", str(run / "ws"),
           "--specs", str(ROOT / "agent" / "kernel_spec")]
    cmd += ["--resume"] if args.resume else [args.goal]
    with open(run / "run.log", "a") as log:
        return subprocess.run(cmd, cwd=ROOT / "agent", stdout=log,
                              stderr=subprocess.STDOUT).returncode


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
