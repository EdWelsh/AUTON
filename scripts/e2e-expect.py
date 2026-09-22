#!/usr/bin/env python3
"""Compare an e2e run to docs/E2E-EXPECTED.yaml.

    scripts/e2e-expect.py [ARTIFACT_DIR]      # default: the newest .artifacts/e2e/*

Exit 0 when the run matches the expectation exactly: the same verdict, the
same failed stage, and exactly the listed markers failing. Exit 1 otherwise,
naming the difference. A marker listed as expected-to-fail that now passes is
also a failure, because the expectation is then stale.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def failing_markers(run: Path) -> list[str]:
    log = run / "6-markers.log"
    if not log.exists():
        return []
    return [line[6:].strip() for line in log.read_text().splitlines()
            if line.startswith("FAIL  ")]


def main(argv: list[str]) -> int:
    runs = sorted((ROOT / ".artifacts" / "e2e").glob("*/"))
    run = Path(argv[1]) if len(argv) > 1 else (runs[-1] if runs else None)
    if run is None or not (run / "summary.json").exists():
        print("no e2e run to compare", file=sys.stderr)
        return 2
    want = yaml.safe_load((ROOT / "docs" / "E2E-EXPECTED.yaml").read_text())
    got = json.loads((run / "summary.json").read_text())
    problems = []

    if got["verdict"] != want["verdict"]:
        problems.append(f"verdict {got['verdict']}, expected {want['verdict']}")
    if want["verdict"] == "RED" and got.get("failed_stage") != want.get("failed_stage"):
        problems.append(f"failed at {got.get('failed_stage')}, expected {want.get('failed_stage')}")

    expected = [m["pattern"] for m in want.get("failing_markers") or []]
    actual = failing_markers(run)
    for m in actual:
        if m not in expected:
            problems.append(f"unexpected failing marker: {m}")
    if got.get("failed_stage") == "markers" or got["verdict"] == "GREEN":
        for m in expected:
            if m not in actual:
                problems.append(f"expected-to-fail marker now passes (update the file): {m}")

    if problems:
        print(f"e2e does not match docs/E2E-EXPECTED.yaml ({run.name}):")
        for p in problems:
            print(f"  - {p}")
        return 1
    note = "; ".join(f"{m['pattern']} until {m['cleared_by']}"
                     for m in want.get("failing_markers") or [])
    print(f"e2e matches expectation: {want['verdict']}" + (f" ({note})" if note else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
