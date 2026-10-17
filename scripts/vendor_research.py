#!/usr/bin/env python3
"""Run the vendor spec agents in a testing area, and collect what passed its checks.

    .venv/bin/python scripts/vendor_research.py start scout-cpu \\
        --goal "Find the documentation for the 5 highest-priority vendors in vendor_queue"
    .venv/bin/python scripts/vendor_research.py start verify-isa \\
        --goal "Verify every exceptions.yaml row with verified: false against its document"
    .venv/bin/python scripts/vendor_research.py collect scout-cpu

A run lives in .artifacts/hardware/<name>/ (gitignored): its own git workspace,
its config and its log. The agents are told to write hardware/proposals/ and
hardware/derived/; what is enforced is that writes stay inside the workspace (absolute
paths, '..' and .auton/ are refused), not which directory in it. `collect` re-runs the same checks the
agents' tool runs and prints the files that pass; a person merges those into
agent/hardware/, so nothing an agent wrote becomes a fact unreviewed.

It spends model calls: on a subscription, start one small goal and read the
result before starting another.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".artifacts" / "hardware"
TEMPLATES = (ROOT / "agent" / "config" / "auton.toml",
             ROOT / "agent" / "config" / "auton.toml.example")
GRACE = 60                  # seconds between SIGTERM (pause) and SIGKILL
sys.path.insert(0, str(ROOT / "agent" / "tools"))


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
    could lack one, and a run that silently kept e.g. its developers would
    write kernel code where it should research."""
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


def config(run: Path, model: str, scouts: int, readers: int) -> Path:
    cfg = run / "auton.toml"
    cfg.write_text(patched(config_template(), {
        "model =": f'model = "{model}"',
        "path =": f'path = "{run / "ws"}"',
        "developer_count": "developer_count = 0",
        "specialists =": "specialists = false",          # a research run writes no kernel code
        "research =": f"research = true\nscout_count = {scouts}\nreader_count = {readers}",
    }))
    return cfg


def start(args) -> int:
    run = OUT / args.name
    if (run / "ws").exists() and not args.resume:
        print(f"{run} exists; pass --resume to continue it", file=sys.stderr)
        return 2
    run.mkdir(parents=True, exist_ok=True)
    cfg = config(run, args.model, args.scouts, args.readers)
    py = os.environ.get("PYTHON") or str(ROOT / ".venv/bin/python")
    cmd = [py, "-m", "orchestrator.cli",
           "--config", str(cfg), "run", "--workspace", str(run / "ws"),
           "--specs", str(ROOT / "agent" / "kernel_spec")]
    cmd += ["--resume"] if args.resume else [args.goal]
    with open(run / "run.log", "a") as log:
        return run_bounded(cmd, ROOT / "agent", log, args.timeout)


def collect(args) -> int:
    import vendor_research as vr

    ws = OUT / args.name / "ws"
    if not ws.is_dir():
        print(f"no run {args.name!r} in {OUT}", file=sys.stderr)
        return 2
    branches = subprocess.run(["git", "-C", str(ws), "branch", "--format=%(refname:short)"],
                              capture_output=True, text=True).stdout.split()
    branches.sort(key=lambda br: br != "main")      # main's copy names a file shared with it
    # A file merged to main is on every branch cut after the merge: one version of
    # one path is one result, listed under the first branch and its others.
    seen: dict[tuple[str, str], list[str]] = {}
    for br in branches:
        listing = subprocess.run(["git", "-C", str(ws), "ls-tree", "-r", br, "hardware/"],
                                 capture_output=True, text=True).stdout.splitlines()
        for entry in listing:
            meta, _, f = entry.partition("\t")
            seen.setdefault((f, meta.split()[2]), []).append(br)
    ok = bad = 0
    for (f, oid), on in seen.items():
        text = subprocess.run(["git", "-C", str(ws), "cat-file", "blob", oid],
                              capture_output=True, text=True).stdout
        errs = vr.check_proposal(text) if f.startswith("hardware/proposals/") \
            else vr.check_derived(text)
        mark = "PASS" if not errs else "FAIL"
        ok, bad = ok + (not errs), bad + bool(errs)
        also = f"  (also on {', '.join(on[1:])})" if len(on) > 1 else ""
        print(f"{mark} {on[0]}:{f}{also}")
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
