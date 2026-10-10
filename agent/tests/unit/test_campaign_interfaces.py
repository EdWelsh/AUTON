"""Every run judged by a frozen suite with a reference gets that interface in its workspace.

Eleven of twelve first-campaign runs failed to compile against names their spec never declared
(w24 F-1); R8, seeded with its header, passed. This keeps the next suite from shipping the hole.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
RUNS = yaml.safe_load((ROOT / "docs/campaign/runs.yaml").read_text())["runs"]


def _reference_for(gate: str) -> str | None:
    m = re.search(r"tests/kernel/run_(\w+)_test\.sh", gate)
    if not m:
        return None
    ref = ROOT / "tests/kernel" / f"{m.group(1)}_reference" / "include"
    return f"tests/kernel/{m.group(1)}_reference/include" if ref.is_dir() else None


def test_each_runs_reference_interface_is_seeded_and_named_in_its_goal():
    missing = []
    for run in RUNS:
        goal = (ROOT / "docs/campaign" / run["goal"]).read_text()
        for gate in run["gates"]:
            ref = _reference_for(gate)
            if ref and (ref not in (run.get("seed") or {}) or ref not in goal):
                missing.append((run["name"], ref))
    assert not missing, f"suite interface not given to the session: {missing}"


def test_the_suites_with_a_reference_cover_most_of_the_campaign():
    covered = [r["name"] for r in RUNS if any(_reference_for(g) for g in r["gates"])]
    assert len(covered) >= 8, covered
