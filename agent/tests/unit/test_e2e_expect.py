"""docs/E2E-EXPECTED.yaml is checked, not trusted: a new failure fails, and so
does an expectation that has gone stale."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "e2e-expect.py"
MM = r"\[MM\] PMM initialized: \d+ pages total, \d+ reserved, \d+ free"


def _run(tmp_path, verdict, stage, failing):
    d = tmp_path / "run"
    d.mkdir()
    (d / "summary.json").write_text(json.dumps({"verdict": verdict, "failed_stage": stage}))
    (d / "6-markers.log").write_text(
        "PASS  \\[BOOT\\] OK\n" + "".join(f"FAIL  {m}\n" for m in failing))
    r = subprocess.run([sys.executable, str(SCRIPT), str(d)], capture_output=True, text=True)
    return r.returncode, r.stdout


def test_the_documented_red_matches(tmp_path):
    rc, out = _run(tmp_path, "RED", "markers", [MM])
    assert rc == 0, out


def test_a_new_failing_marker_fails(tmp_path):
    rc, out = _run(tmp_path, "RED", "markers", [MM, r"\[SLM\] Ready"])
    assert rc == 1 and "unexpected failing marker" in out


def test_a_stale_expectation_fails(tmp_path):
    """The PMM is generated, the marker passes, and the file still says red."""
    rc, out = _run(tmp_path, "GREEN", None, [])
    assert rc == 1 and "now passes" in out


def test_failing_earlier_than_expected_fails(tmp_path):
    rc, out = _run(tmp_path, "RED", "parity", [])
    assert rc == 1 and "failed at parity" in out
