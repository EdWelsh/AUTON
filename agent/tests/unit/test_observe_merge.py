"""observe.merge keeps what the static reading said (w23 C4)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from observe import merge  # noqa: E402

OBS = {"id": "obs-1", "facts": [{"capability": "listen:tcp/8000"},
                                {"capability": "runtime:python-3.12"},
                                {"capability": "lib:libssl.so.3"}]}


def _record(tmp_path, facts):
    p = tmp_path / "a.yaml"
    p.write_text(yaml.safe_dump({"facts": facts}))
    return p


def test_a_declared_fact_that_is_observed_remembers_it_was_declared(tmp_path):
    ev = [{"file": "app.py", "line": 3, "quote": "app.run(port=8000)"}]
    rec = _record(tmp_path, [{"capability": "listen:tcp/8000", "source": "declared",
                              "evidence": ev}])
    fact = merge(rec, OBS)["facts"][0]
    assert fact["source"] == "observed" and fact["static_source"] == "declared"
    assert fact["observation"] == "obs-1" and fact["evidence"] == ev


def test_an_inferred_fact_keeps_inferred(tmp_path):
    rec = _record(tmp_path, [{"capability": "lib:libssl.so.3", "source": "inferred"}])
    assert merge(rec, OBS)["facts"][0]["static_source"] == "inferred"


def test_merging_twice_does_not_overwrite_the_static_source(tmp_path):
    rec = _record(tmp_path, [{"capability": "listen:tcp/8000", "source": "declared"}])
    once = merge(rec, OBS)
    rec.write_text(yaml.safe_dump(once))
    twice = merge(rec, {**OBS, "id": "obs-2"})
    fact = twice["facts"][0]
    assert fact["static_source"] == "declared" and fact["observation"] == "obs-2"


def test_a_newly_observed_fact_has_no_static_source(tmp_path):
    rec = _record(tmp_path, [])
    facts = {f["capability"]: f for f in merge(rec, OBS)["facts"]}
    assert "static_source" not in facts["listen:tcp/8000"]
    assert "runtime:python-3.12" not in facts
