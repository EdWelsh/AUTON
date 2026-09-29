"""Only observe.py may write `source: observed` — enforced from both sides (A5).

Mirrors test_probe_ingest.py's guarantee for `probed`: a promise about who may
write a word is worthless if the rest of the codebase can stamp it freely.

1. No module outside observe*.py sets a source to "observed".
2. Everything observe.py emits says "observed" and names its observation.
3. A record an agent wrote is refused if it claims `observed` (A4's gate).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from observe import observation_record  # noqa: E402
from observe_parse import observe_text  # noqa: E402

WRITERS = {"observe.py", "observe_parse.py"}
STAMP = re.compile(r"""["']source["']\s*:\s*["']observed["']|source\s*=\s*["']observed["']""")


def test_no_other_module_stamps_observed():
    offenders = []
    for py in (ROOT / "agent").rglob("*.py"):
        if "tests" in py.parts or py.name in WRITERS or ".venv" in py.parts:
            continue
        if STAMP.search(py.read_text(errors="replace")):
            offenders.append(str(py.relative_to(ROOT)))
    assert offenders == [], offenders


def test_everything_observe_emits_is_observed_and_attributed(tmp_path):
    trace = (ROOT / "agent/tests/fixtures/traces/dlopen-only.strace").read_text()
    rec = observation_record(observe_text(trace), trace=trace, subject=tmp_path,
                             image="sha256:x", command=["x"], exercise="", exercise_exit=0,
                             duration=1.0)
    assert rec["facts"]
    for fact in rec["facts"]:
        assert fact["source"] == "observed" and fact["observation"] == rec["id"]
    assert "nothing else" in rec["coverage"]
