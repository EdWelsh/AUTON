"""Artifact → Manifest: a second constructor, not a second pipeline (A6).

An application enters through the same door a sentence does: the same
`Manifest` dataclass, the same slice closure, the same refusal with the path
that caused it. Two gates: a contradictory artifact is refused exactly as a
contradictory sentence is, and nothing downstream changed to make room — which
`test_sentence_manifests_are_byte_identical` holds against JSON captured before
this code existed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

import intent_manifest  # noqa: E402
from artifact_manifest import SUBSTRATES, build_from_artifact, main  # noqa: E402
from intent_manifest import IntentError, Manifest  # noqa: E402

FIXTURES = ROOT / "agent" / "tests" / "fixtures"
VALID = FIXTURES / "artifacts" / "valid.artifact.yaml"
SUBJECT = FIXTURES / "apps" / "flask-hello"
GOLDEN = FIXTURES / "artifacts" / "golden_sentence_manifests.json"


def _write(tmp_path, mutate=None) -> Path:
    data = yaml.safe_load(VALID.read_text())
    if mutate:
        mutate(data)
    p = tmp_path / "app.artifact.yaml"
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    return p


# --------------------------------------------------------------------------- #
# Downstream unchanged
# --------------------------------------------------------------------------- #

def test_sentence_manifests_are_byte_identical():
    golden = json.loads(GOLDEN.read_text())
    for name, case in golden.items():
        assert intent_manifest.build(case["sentence"]).to_json() == case["json"], name


def test_the_consumers_did_not_change():
    """The PRD's metric: zero downstream files changed to accommodate the
    artifact path. Measured over A6's own change — from the commit before it
    to the commit that added artifact_manifest.py (or the working tree, before
    that commit exists) — so later, unrelated edits to a consumer do not trip it."""
    consumers = ["agent/tools/intent_service.py", "agent/tools/package_image.py",
                 "agent/tools/errata_join.py", "agent/tools/target_spec.py",
                 "agent/tools/build_service.py", "agent/tools/capability_slice.py"]

    def git(*args):
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    added = git("log", "--diff-filter=A", "--format=%H", "--",
                "agent/tools/artifact_manifest.py").stdout.split()
    if added:
        a6 = added[-1]
        diff = git("diff", "--stat", f"{a6}^", a6, "--", *consumers)
    else:
        diff = git("diff", "--stat", "HEAD", "--", *consumers)
    if diff.returncode != 0:
        pytest.skip(f"git history unavailable: {diff.stderr.strip()}")
    assert diff.stdout == "", diff.stdout


# --------------------------------------------------------------------------- #
# Container substrates
# --------------------------------------------------------------------------- #

def test_a_valid_artifact_becomes_the_same_dataclass():
    m = build_from_artifact(VALID, substrate="docker", subject=SUBJECT)
    assert isinstance(m, Manifest)
    assert m.matched == "artifact"
    assert m.intent.startswith("application:flask-hello@")
    app = m.application
    assert app["substrate"] == "docker"
    assert app["runtime"] == "runtime:python-3.12"
    assert "lib:libssl.so.3" in app["requires"] and "listen:tcp/8000" in app["requires"]


def test_a_container_substrate_does_not_touch_the_kernel_slice(monkeypatch):
    import artifact_manifest

    def boom(*_a, **_k):
        raise AssertionError("capability_slice called for a container substrate")
    monkeypatch.setattr(artifact_manifest, "capability_slice", boom)
    m = build_from_artifact(VALID, substrate="docker")
    assert m.requires == [] and m.excludes == []


def test_assumptions_and_decisions_carry_provenance():
    m = build_from_artifact(VALID, substrate="docker")
    assert any("listen:tcp/8000" in a and "declared only" in a for a in m.assumptions)
    assert any("path:/etc/ssl/certs" in a for a in m.assumptions)
    by_cap = {d["capability"]: d for d in m.decisions}
    assert by_cap["lib:libssl.so.3"]["source"] == "inferred"
    assert by_cap["lib:libssl.so.3"]["because"] == "app.py:2: import ssl"


def test_an_invalid_artifact_is_refused_with_its_problems(tmp_path):
    bad = _write(tmp_path, lambda d: d["facts"][0].update(capability="lib:libmagic.so.9"))
    with pytest.raises(IntentError, match="libmagic.so.9"):
        build_from_artifact(bad, substrate="docker")


def test_a_record_whose_quotes_do_not_check_out_is_refused(tmp_path):
    bad = _write(tmp_path, lambda d: d["facts"][0]["evidence"][0].update(quote="import OpenSSL"))
    with pytest.raises(IntentError, match="import OpenSSL"):
        build_from_artifact(bad, substrate="docker", subject=SUBJECT)


def test_an_unknown_substrate_lists_the_known_ones():
    with pytest.raises(IntentError, match=", ".join(SUBSTRATES)):
        build_from_artifact(VALID, substrate="mainframe")


# --------------------------------------------------------------------------- #
# The AUTON-kernel substrate
# --------------------------------------------------------------------------- #

def _auton_only(data):
    """A static binary that listens on a port: the case that bridges."""
    data["runtime"] = {"capability": "runtime:static-elf", "source": "declared",
                       "evidence": [{"file": "Dockerfile", "line": 1,
                                     "quote": "FROM python:3.12-slim"}]}
    data["facts"] = [f for f in data["facts"] if f["capability"] == "listen:tcp/8000"]


def test_a_bridged_artifact_resolves_to_kernel_capabilities(tmp_path):
    m = build_from_artifact(_write(tmp_path, _auton_only), substrate="auton")
    assert "tcp" in m.requires and "sockets" in m.requires
    assert set(intent_manifest.BASE_REQUIRES) <= set(m.requires)
    assert m.excludes, "excludes are derived, so minimal is testable"
    assert any("assuming e1000" in a for a in m.assumptions), \
        "no target: the network driver is a recorded assumption, as for a sentence"


def test_a_contradictory_artifact_is_refused_with_the_path(tmp_path):
    with pytest.raises(IntentError) as exc:
        build_from_artifact(_write(tmp_path, _auton_only), substrate="auton", excludes=["mm"])
    msg = str(exc.value)
    assert "path: mm" in msg and "self-contradictory" in msg, \
        "refused with the dependency path, exactly as a sentence is"


def test_an_unbridged_fact_on_the_auton_substrate_is_refused(tmp_path):
    with pytest.raises(IntentError) as exc:
        build_from_artifact(VALID, substrate="auton")
    msg = str(exc.value)
    assert "lib:libssl.so.3" in msg and "no POSIX" in msg and "container" in msg


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def test_cli(tmp_path, capsys):
    assert main([str(VALID), "--substrate", "docker"]) == 0
    assert json.loads(capsys.readouterr().out)["application"]["substrate"] == "docker"
    assert main([str(VALID), "--substrate", "auton"]) == 1
    assert "DECLINED" in capsys.readouterr().err
