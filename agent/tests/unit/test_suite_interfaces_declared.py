"""w24 F-1: a frozen suite's interface must reach the session that has to match it.

Six runs failed gate 1 because the suite named identifiers (KV_SHUTDOWN, FS_PATH_MAX, ...) that
only live in tests/kernel/<x>_reference/include and the session never received. For every campaign
run whose gate is run_<x>_test.sh with a <x>_reference tree, the run must seed that include
directory and its goal must name it.
"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
RUNS = yaml.safe_load((ROOT / "docs/campaign/runs.yaml").read_text())
GATE = re.compile(r"run_(\w+?)_test\.sh")


def _cases(runs: list[dict]) -> list[tuple[str, str, dict]]:
    out = []
    for run in runs:
        for gate in run.get("gates", []):
            m = GATE.search(gate)
            if m and (ROOT / "tests/kernel" / f"{m.group(1)}_reference").is_dir():
                out.append((run["name"], m.group(1), run))
    return out


def _runs() -> list[dict]:
    return RUNS["runs"] if isinstance(RUNS, dict) else RUNS


CASES = _cases(_runs())


def test_the_check_sees_the_campaign():
    assert len(CASES) >= 8


@pytest.mark.parametrize("name,suite,run", CASES, ids=[f"{c[0]}:{c[1]}" for c in CASES])
def test_reference_interface_is_seeded_and_named(name, suite, run):
    include = f"tests/kernel/{suite}_reference/include"
    assert (ROOT / include).is_dir(), f"{include} does not exist"
    assert include in (run.get("seed") or {}), f"{name} does not seed {include}"
    goal = (ROOT / "docs/campaign" / run["goal"]).read_text()
    assert f"{suite}_reference" in goal, f"{name}'s goal never names {suite}_reference"
