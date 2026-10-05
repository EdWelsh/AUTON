#!/usr/bin/env python3
"""Run the generation campaign (docs/campaign/runs.yaml), unattended, in order.

    .venv/bin/python scripts/campaign.py            # run whatever is not finished
    .venv/bin/python scripts/campaign.py --status   # print each run's verdict

Each run goes through scripts/generation_run.py. The campaign adds what lies
between runs:

- **Order and dependencies.** `base: run:<name>` builds on that run's resulting
  tree — if it passed every gate. If it did not, the dependant starts from that
  run's own base (recursively), the last good tree, and RESULT.json says so.
- **Stop rules** (docs/CAMPAIGN.md): at most two attempts per phase. Attempt 2
  runs automatically, identical except for its label; then the phase is
  recorded as failed and the ladder continues.
- **Resumable.** A run directory with a finished RESULT.json is not re-run; one
  without resumes where it stopped. Killing this script loses nothing.

Everything lands in .artifacts/campaign/<name>-attempt<k>/ and the campaign's
own log, .artifacts/campaign/campaign.log.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/campaign/runs.yaml"
OUT = ROOT / ".artifacts/campaign"
MAX_ATTEMPTS = 2
# A run that ends "not generated" on every gate this quickly did not fail on
# the model's merits: the harness broke (w18: a parse defect raced the campaign
# through R1, R8, R2 and R3 in minutes, spending their attempts). Stop instead.
HARNESS_SUSPECT_SECONDS = 1800


def harness_suspect(r: dict) -> bool:
    gates = r.get("gates") or []
    spent = sum(s.get("seconds", 0) for s in r.get("sessions", []))
    return bool(gates) and all(g["rc"] == 2 for g in gates) and spent < HARNESS_SUSPECT_SECONDS


def log(msg: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} {msg}"
    print(line, flush=True)
    with open(OUT / "campaign.log", "a") as fh:
        fh.write(line + "\n")


def result_of(run_dir: Path) -> dict | None:
    p = run_dir / "RESULT.json"
    if not p.exists():
        return None
    r = json.loads(p.read_text())
    return r if "finished" in r else None


def passed(r: dict | None) -> bool:
    return bool(r and r.get("gates") and all(g["rc"] == 0 for g in r["gates"]))


def attempts(run: dict) -> list[Path]:
    first = int(run.get("attempt", 1))
    return [OUT / f"{run['name']}-attempt{k}" for k in range(first, MAX_ATTEMPTS + 1)]


def final(run: dict) -> tuple[Path | None, dict | None]:
    """The run's last finished attempt and its result."""
    last = (None, None)
    for d in attempts(run):
        r = result_of(d)
        if r is not None:
            last = (d, r)
            if passed(r):
                break
    return last


def base_for(run: dict, runs: dict[str, dict]) -> tuple[list[str], str]:
    """generation_run arguments for the run's base, and a note on how chosen."""
    base = run["base"]
    if not base.startswith("run:"):
        return ["--base-rev", base], base
    dep = runs[base[4:]]
    d, r = final(dep)
    if passed(r):
        return ["--base-tree", str(d / "ws")], f"{dep['name']} (passed)"
    args, note = base_for(dep, runs)
    return args, f"{note} — {dep['name']} did not pass, so its own base"


def run_one(run: dict, runs: dict[str, dict], spec: dict) -> None:
    for d in attempts(run):
        r = result_of(d)
        if r is None:
            base_args, note = base_for(run, runs)
            log(f"{run['name']}: {d.name} starting on {note}")
            cmd = [sys.executable, str(ROOT / "scripts/generation_run.py"),
                   "--run", d.name, "--out", str(d),
                   "--goal", str(ROOT / "docs/campaign" / run["goal"]),
                   "--model", spec["model"], "--sessions", str(run.get("sessions", 2)),
                   "--session-seconds", str(spec.get("session_seconds", 18000)),
                   "--context", str(spec.get("context", 32768)), *base_args]
            for dest, src in (run.get("seed") or {}).items():
                cmd += ["--seed", f"{dest}={src}"]
            for gate in run["gates"]:
                cmd += ["--gate", gate]
            for gate in run.get("advisory") or []:
                cmd += ["--advisory", gate]
            subprocess.run(cmd, cwd=ROOT)
            r = result_of(d)
            if r is None:
                log(f"{run['name']}: {d.name} stopped without a result; rerun the campaign to resume it")
                raise SystemExit(1)
        verdicts = ", ".join(f"{g['rc']}" for g in r.get("gates", []))
        if harness_suspect(r):
            log(f"{run['name']}: {d.name} STOPPED — not generated on every gate after "
                f"{sum(s.get('seconds', 0) for s in r.get('sessions', []))} s: a harness failure, "
                f"not a result. Investigate, archive the directory, and rerun.")
            raise SystemExit(3)
        if passed(r):
            log(f"{run['name']}: {d.name} PASSED every gate ({verdicts})")
            return
        log(f"{run['name']}: {d.name} did not pass (gate exits {verdicts})")
    log(f"{run['name']}: failed after {MAX_ATTEMPTS} attempts; fallback {run.get('fallback', 'none')} — "
        f"the ladder continues on the last good tree")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--only", help="run just this one (by name)")
    args = ap.parse_args(argv)
    spec = yaml.safe_load(SPEC.read_text())
    runs = {r["name"]: r for r in spec["runs"]}

    if args.status:
        for r in spec["runs"]:
            d, res = final(r)
            state = ("PASSED" if passed(res) else "failed" if res else "not finished")
            gates = [g["rc"] for g in res.get("gates", [])] if res else []
            print(f"{r['name']:20} {state:13} {d.name if d else '-':28} gates {gates}")
        return 0

    for name in [r["name"] for r in spec["runs"]]:
        if args.only and name != args.only:
            continue
        # Re-read before each run: a dated amendment to a later run's gate
        # (stop rule 5) takes effect without stopping the run in progress.
        spec = yaml.safe_load(SPEC.read_text())
        runs = {r["name"]: r for r in spec["runs"]}
        run_one(runs[name], runs, spec)
    log("campaign: every run has a verdict")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
