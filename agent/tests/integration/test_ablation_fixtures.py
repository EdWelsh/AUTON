"""The A9 gate on Docker: the score can see an over-claim.

A manifest for flask-hello with one requirement seeded that the app never
uses (lib:libsqlite3.so.0 — present in the base, loaded by nothing the app
imports). A score reporting everything load-bearing here would prove it cannot
see over-claim, and would fail the phase.

It also finds a real one: the fixture record lists path:/etc/ssl/certs as
`unknown`, and ablation shows this application does not need it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from package_gate import load_bases  # noqa: E402

AGENT = ROOT / "agent"
SUBJECT = AGENT / "tests" / "fixtures" / "apps" / "flask-hello"
PROBE = AGENT / "tests" / "fixtures" / "probes" / "flask-hello.yaml"
RECORD = AGENT / "tests" / "fixtures" / "artifacts" / "valid.artifact.yaml"


def _docker_ok() -> bool:
    return bool(shutil.which("docker")) and subprocess.run(
        ["docker", "info"], capture_output=True).returncode == 0


pytestmark = pytest.mark.skipif(not _docker_ok(), reason="no Docker daemon")


def test_the_score_sees_a_seeded_over_claim_and_a_real_one(tmp_path):
    from ablate import ablate
    from artifact_manifest import build_from_artifact

    ws = tmp_path / "ws"
    (ws / ".auton").mkdir(parents=True)
    (ws / "package").mkdir()
    shutil.copytree(SUBJECT, ws / ".auton" / "subject")
    manifest = json.loads(build_from_artifact(RECORD, "docker").to_json())
    manifest["application"]["requires"].append("lib:libsqlite3.so.0")
    (ws / ".auton" / "manifest.json").write_text(json.dumps(manifest))
    (ws / "package" / "Dockerfile").write_text(
        f"FROM {load_bases()['runtime:python-3.12']}\nWORKDIR /app\n"
        "COPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\n"
        'COPY app.py .\nCMD ["python", "app.py"]\n')

    score = ablate(ws, PROBE)
    by_cap = {s.capability: s for s in score.steps}

    assert score.baseline.startswith("WORKED")
    assert by_cap["lib:libssl.so.3"].outcome == "load-bearing"
    assert "libssl.so.3" in by_cap["lib:libssl.so.3"].detail
    assert by_cap["lib:libsqlite3.so.0"].outcome == "over-claimed", "the seeded over-claim"
    assert by_cap["path:/etc/ssl/certs"].outcome == "over-claimed", "a real one"
    assert score.load_bearing < score.ablated, "N of N here would mean it cannot see over-claim"
    assert (ws / "package" / "ABLATION.json").is_file()
    assert all(s.seconds < 300 for s in score.steps), "cost per step is measured"
