"""Evidence discipline (A4): a finding must be checkable, and is checked.

A citation is only evidence if the cited line says what the quote says. These
tests aim the adversarial cases at the validator directly; the loop-level test
(`orchestrator/test_analyst_loop.py`) shows the same refusals reaching an agent
before any reviewer model sees the record.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from artifact_spec import validate  # noqa: E402

FIXTURES = ROOT / "agent" / "tests" / "fixtures"
SUBJECT = FIXTURES / "apps" / "flask-hello"
VALID = FIXTURES / "artifacts" / "valid.artifact.yaml"


@pytest.fixture
def subject(tmp_path):
    dest = tmp_path / "subject"
    shutil.copytree(SUBJECT, dest)
    return dest


def _write(tmp_path, data):
    p = tmp_path / "app.artifact.yaml"
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    return p


def _record():
    return yaml.safe_load(VALID.read_text())


def test_the_valid_record_checks_out_against_its_subject(subject):
    report = validate(VALID, subject=subject, allow_observed=False)
    assert report.ok, report.problems


def test_a_fabricated_quote_is_refused_with_both_strings(tmp_path, subject):
    data = _record()
    data["facts"][0]["evidence"][0]["quote"] = "import OpenSSL"
    [problem] = validate(_write(tmp_path, data), subject=subject).problems
    assert "import OpenSSL" in problem and "import ssl" in problem
    assert "app.py:2" in problem


def test_whitespace_is_not_a_fabrication(tmp_path, subject):
    data = _record()
    data["facts"][0]["evidence"][0]["quote"] = "  import   ssl "
    assert validate(_write(tmp_path, data), subject=subject).ok


def test_a_line_past_the_end_is_refused(tmp_path, subject):
    data = _record()
    data["facts"][0]["evidence"][0]["line"] = 400
    [problem] = validate(_write(tmp_path, data), subject=subject).problems
    assert "lines" in problem


def test_a_file_the_subject_does_not_have_is_refused(tmp_path, subject):
    data = _record()
    data["facts"][0]["evidence"][0]["file"] = "vendor/ssl_shim.py"
    [problem] = validate(_write(tmp_path, data), subject=subject).problems
    assert "vendor/ssl_shim.py" in problem and "no such file" in problem


@pytest.mark.parametrize("escape", ["../../../etc/passwd", "/etc/passwd"])
def test_evidence_cannot_cite_outside_the_subject(tmp_path, subject, escape):
    data = _record()
    data["facts"][0]["evidence"][0]["file"] = escape
    [problem] = validate(_write(tmp_path, data), subject=subject).problems
    assert "outside the subject" in problem


def test_an_agent_written_observed_fact_is_refused(tmp_path, subject):
    data = _record()
    data["facts"].append({"capability": "lib:libz.so.1", "source": "observed",
                          "observation": "made-up"})
    [problem] = validate(_write(tmp_path, data), subject=subject,
                         allow_observed=False).problems
    assert "observe.py" in problem


def test_a_record_for_a_different_tree_is_refused(tmp_path, subject):
    (subject / "app.py").write_text("changed\n")
    report = validate(VALID, subject=subject)
    assert any("tree_hash" in p and "staged subject" in p for p in report.problems)


def test_the_phantom_capability_refusal_lists_the_known_names(tmp_path, subject):
    data = _record()
    data["facts"][0]["capability"] = "lib:libmagic-unicorn.so"
    [problem] = validate(_write(tmp_path, data), subject=subject).problems
    assert "Known lib names" in problem and "libssl.so.3" in problem


def test_an_inferred_port_is_refused(tmp_path, subject):
    data = _record()
    data["facts"][1]["source"] = "inferred"
    problems = validate(_write(tmp_path, data), subject=subject).problems
    assert any("listen:tcp/8000" in p and "inferred" in p for p in problems)


def test_a_form_feed_does_not_shift_line_numbers(tmp_path, subject):
    """splitlines() breaks on \\f, so line numbers drifted from grep -n."""
    (subject / "app.py").write_text("import os\n\f# page two\nimport ssl\n")
    data = _record()
    data["subject"]["tree_hash"] = __import__("artifact_spec").subject_hash.tree_hash(subject)
    data["facts"][0]["evidence"][0].update(line=3, quote="import ssl")
    data["facts"][3]["evidence"][0].update(line=1, quote="import os")
    report = validate(_write(tmp_path, data), subject=subject)
    assert report.ok, report.problems
