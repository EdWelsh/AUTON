"""The A5 gate: what static reading misses, observation catches.

`dlopen-only` builds its library's name at run time from plugins.conf. No
soname appears in any source file, so a static reading cannot name it; running
it in the sandbox does. If both found it, or neither did, one of the two would
not be doing its job (PRD, A5).

Needs a Docker daemon; skipped, with the reason, without one. CI's Linux leg
has one.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

APPS = ROOT / "agent" / "tests" / "fixtures" / "apps"
SONAME = re.compile(r"lib[A-Za-z0-9_+-]+\.so(\.[0-9]+)*")


def _docker_ok() -> bool:
    return bool(shutil.which("docker")) and subprocess.run(
        ["docker", "info"], capture_output=True).returncode == 0


pytestmark = pytest.mark.skipif(not _docker_ok(), reason="no Docker daemon")


def test_static_reading_misses_it_and_observation_catches_it(tmp_path):
    from observe import observe

    subject = APPS / "dlopen-only"
    static = {m.group(0) for f in subject.iterdir() if f.is_file()
              for m in SONAME.finditer(f.read_text(errors="replace"))}
    assert "libz.so.1" not in static, "the fixture would not test anything"

    obs = observe(subject)
    caps = {f["capability"] for f in obs["facts"]}
    assert "lib:libz.so.1" in caps
    assert obs["exercise_exit"] == 0


def test_observed_facts_merge_into_a_record_and_validate(tmp_path):
    from artifact_spec import subject_hash, validate
    from observe import observe

    subject = APPS / "dlopen-only"
    record = tmp_path / "analysis" / "dlopen-only.artifact.yaml"
    record.parent.mkdir()
    record.write_text(yaml.safe_dump({
        "format": 1, "application": "dlopen-only",
        "subject": {"repo": str(subject), "commit": None,
                    "tree_hash": subject_hash.tree_hash(subject)},
        "runtime": {"capability": "runtime:glibc-elf", "source": "declared",
                    "evidence": [{"file": "Dockerfile", "line": 6,
                                  "quote": "RUN gcc -O1 -o /app/plugin-host main.c -ldl"}]},
        "facts": [{"capability": "lib:libz.so.1", "source": "unknown",
                   "looked_at": ["main.c", "plugins.conf"]}],
    }, sort_keys=False))

    obs = observe(subject, record=record)
    merged = yaml.safe_load(record.read_text())
    [z] = [f for f in merged["facts"] if f["capability"] == "lib:libz.so.1"]
    assert z["source"] == "observed" and z["observation"] == obs["id"]
    assert (record.parent / "observations" / f"{obs['id']}.json").is_file()
    assert validate(record, subject=subject, allow_observed=True).ok
