#!/usr/bin/env python3
"""Run the vendor spec agents in a testing area, and collect what passed its checks.

    .venv/bin/python scripts/vendor_research.py start scout-cpu \\
        --goal "Find the documentation for the 5 highest-priority vendors in vendor_queue"
    .venv/bin/python scripts/vendor_research.py start verify-isa \\
        --goal "Verify every exceptions.yaml row with verified: false against its document"
    .venv/bin/python scripts/vendor_research.py collect scout-cpu

A run lives in .artifacts/hardware/<name>/ (gitignored): its own git workspace,
its config and its log. The agents write hardware/proposals/ and
hardware/derived/ there and nowhere else. `collect` re-runs the same checks the
agents' tool runs and prints the files that pass; a person merges those into
agent/hardware/, so nothing an agent wrote becomes a fact unreviewed.

It spends model calls: on a subscription, start one small goal and read the
result before starting another.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".artifacts" / "hardware"
TEMPLATE = ROOT / "agent" / "config" / "auton.toml.example"
sys.path.insert(0, str(ROOT / "agent" / "tools"))


def config(run: Path, model: str, scouts: int, readers: int) -> Path:
    lines = []
    for line in TEMPLATE.read_text().splitlines():
        if line.startswith("model ="):
            line = f'model = "{model}"'
        elif line.startswith("path ="):
            line = f'path = "{run / "ws"}"'
        elif line.startswith("developer_count"):
            line = "developer_count = 0"
        elif line.startswith("specialists ="):
            line = "specialists = false"          # a research run writes no kernel code
        elif line.startswith("research ="):
            line = f"research = true\nscout_count = {scouts}\nreader_count = {readers}"
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
    cfg = config(run, args.model, args.scouts, args.readers)
    py = os.environ.get("PYTHON") or str(ROOT / ".venv/bin/python")
    cmd = ["timeout", "-k", "60", str(args.timeout), py, "-m", "orchestrator.cli",
           "--config", str(cfg), "run", "--workspace", str(run / "ws"),
           "--specs", str(ROOT / "agent" / "kernel_spec")]
    cmd += ["--resume"] if args.resume else [args.goal]
    with open(run / "run.log", "a") as log:
        return subprocess.run(cmd, cwd=ROOT / "agent", stdout=log, stderr=subprocess.STDOUT).returncode


def collect(args) -> int:
    import vendor_research as vr

    ws = OUT / args.name / "ws"
    if not ws.is_dir():
        print(f"no run {args.name!r} in {OUT}", file=sys.stderr)
        return 2
    branches = subprocess.run(["git", "-C", str(ws), "branch", "--format=%(refname:short)"],
                              capture_output=True, text=True).stdout.split()
    ok = bad = 0
    for br in branches:
        files = subprocess.run(["git", "-C", str(ws), "ls-tree", "-r", "--name-only", br,
                                "hardware/"], capture_output=True, text=True).stdout.split()
        for f in files:
            text = subprocess.run(["git", "-C", str(ws), "show", f"{br}:{f}"],
                                  capture_output=True, text=True).stdout
            errs = vr.check_proposal(text) if f.startswith("hardware/proposals/") \
                else vr.check_derived(text)
            mark = "PASS" if not errs else "FAIL"
            ok, bad = ok + (not errs), bad + bool(errs)
            print(f"{mark} {br}:{f}")
            for e in errs[:5]:
                print(f"     {e}")
    print(f"{ok} pass, {bad} fail. Merge PASS files into agent/hardware/ by hand, after reading them.")
    return 0 if bad == 0 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("name")
    s.add_argument("--goal")
    s.add_argument("--resume", action="store_true")
    s.add_argument("--model", default="claude-cli/claude-sonnet-5-5")
    s.add_argument("--scouts", type=int, default=1)
    s.add_argument("--readers", type=int, default=1)
    s.add_argument("--timeout", type=int, default=3600)
    c = sub.add_parser("collect")
    c.add_argument("name")
    args = ap.parse_args(argv)
    if args.cmd == "start" and not (args.goal or args.resume):
        ap.error("start needs --goal (or --resume)")
    return start(args) if args.cmd == "start" else collect(args)


if __name__ == "__main__":
    raise SystemExit(main())
