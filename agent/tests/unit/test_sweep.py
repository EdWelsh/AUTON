"""The unmitigated sweep (H12): buckets, and the claims it refuses."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from sweep import EvidenceError, classify, load_evidence  # noqa: E402


def rec(status="No Fix", workaround="None identified.", title="T", key="ADL999"):
    return SimpleNamespace(key=key, title=title, status=status, workaround=workaround)


NONE_FOUND = {"evidence": [
    {"os": "linux", "kind": "none-found", "checked": "2026-09-22"},
    {"os": "freebsd", "kind": "none-found", "checked": "2026-09-22"},
    {"os": "windows", "kind": "not-checked"}]}


def test_no_fix_no_workaround_none_found_is_documented_unmitigated():
    row = classify(rec(), NONE_FOUND)
    assert row.bucket == "documented-unmitigated"
    assert "linux" in row.why and "freebsd" in row.why and "2026-09-22" in row.why
    assert "windows" not in row.why, "Windows was not searched and must not be claimed"


def test_none_identified_is_not_a_workaround():
    assert classify(rec(workaround="None identified. Software should..."), NONE_FOUND).bucket \
        == "documented-unmitigated"


def test_a_real_workaround_is_vendor_workaround():
    assert classify(rec(workaround="Software should write SP."), NONE_FOUND).bucket \
        == "vendor-workaround"


def test_fixed_and_removed():
    assert classify(rec(status="Fixed"), None).bucket == "vendor-fixed"
    assert classify(rec(status="N/A", title="N/A. Erratum has been removed."), None).bucket \
        == "removed"


def test_not_checked_never_merges_with_none_found():
    assert classify(rec(), None).bucket == "not-checked"
    only_windows = {"evidence": [{"os": "windows", "kind": "not-checked"}]}
    assert classify(rec(), only_windows).bucket == "not-checked"


def test_an_unreviewed_candidate_is_pending():
    ev = {"evidence": [{"os": "linux", "kind": "candidate", "evidence_url": "https://x"}]}
    assert classify(rec(), ev).bucket == "pending-review"


def test_a_confirmed_mitigation_is_os_mitigated():
    ev = {"evidence": [{"os": "linux", "kind": "kernel-workaround", "evidence_url": "https://x"}]}
    assert classify(rec(), ev).bucket == "os-mitigated"


def test_a_mitigation_claim_without_a_source_is_refused(tmp_path):
    p = tmp_path / "e.yaml"
    p.write_text("errata:\n  ADL1:\n    evidence:\n    - {os: linux, kind: microcode}\n")
    with pytest.raises(EvidenceError, match="no evidence_url"):
        load_evidence(p)


def test_a_rejected_hit_counts_as_searched():
    ev = {"evidence": [
        {"os": "linux", "kind": "rejected", "evidence_url": "https://x", "checked": "2026-09-22",
         "why": "perf tags the event; no workaround"},
        {"os": "freebsd", "kind": "none-found", "checked": "2026-09-22"}]}
    row = classify(rec(), ev)
    assert row.bucket == "documented-unmitigated"
    assert "linux" in row.why
