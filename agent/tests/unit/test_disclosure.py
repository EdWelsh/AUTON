"""Private findings and the embargo clock.

The PRD: *"A finding with no disclosure path is not a deliverable."* This exists
before the conformance harness so the first real finding does not have to invent
a process in a hurry.

The refusals carry the weight. A finding is private until disclosure, and a git
commit is publication — so writing one into a tracked path is the failure this
whole policy exists to prevent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from disclosure import (  # noqa: E402
    STATUSES,
    DisclosureError,
    due,
    load_all,
    record,
    set_status,
)

GOOD = dict(silicon="6:151:2", vendor="intel",
            spec_citation="SDM vol 2A, CMPXCHG8B",
            expected="#UD", observed="hang",
            reproducer="execute F0 0F C7 C8 in ring 3", klass="fault")


class TestPrivacy:
    def test_a_tracked_path_is_refused(self):
        """A commit is publication. This is the one refusal that matters most."""
        with pytest.raises(DisclosureError, match="a commit is"):
            record(**GOOD, store=ROOT / "agent" / "hardware")

    def test_the_default_store_is_gitignored(self):
        text = (ROOT / ".gitignore").read_text()

        assert ".disclosure/" in text

    def test_no_finding_is_tracked(self):
        import subprocess

        out = subprocess.run(["git", "ls-files"], cwd=ROOT,
                             capture_output=True, text=True).stdout
        assert not [f for f in out.splitlines() if f.startswith(".disclosure")]


class TestAFindingNeedsProvenance:
    @pytest.mark.parametrize("field", ["spec_citation", "expected", "observed", "reproducer"])
    def test_a_missing_field_is_refused_with_the_reason(self, tmp_path, field):
        bad = {**GOOD, field: ""}
        with pytest.raises(DisclosureError, match="rumour|required"):
            record(**bad, store=tmp_path)

    def test_vague_silicon_is_refused(self, tmp_path):
        with pytest.raises(DisclosureError, match="not a finding"):
            record(**{**GOOD, "silicon": "some intel chips"}, store=tmp_path)

    def test_a_vendor_with_no_published_contact_is_refused(self, tmp_path):
        """A finding cannot be filed against a vendor nobody knows how to
        reach."""
        with pytest.raises(DisclosureError, match="no published security contact"):
            record(**{**GOOD, "vendor": "cyberdyne"}, store=tmp_path)

    def test_the_refusal_lists_the_vendors_that_do_have_one(self, tmp_path):
        with pytest.raises(DisclosureError) as exc:
            record(**{**GOOD, "vendor": "cyberdyne"}, store=tmp_path)

        assert "intel" in str(exc.value) and "arm" in str(exc.value)

    def test_an_unknown_class_is_refused(self, tmp_path):
        with pytest.raises(DisclosureError, match="class must be"):
            record(**{**GOOD, "klass": "vibes"}, store=tmp_path)


class TestRecording:
    def test_a_finding_gets_an_id_and_an_embargo(self, tmp_path):
        f = record(**GOOD, store=tmp_path)

        assert f.id.startswith("AUTON-")
        assert f.embargo_until
        assert f.status == "private"

    def test_the_same_divergence_is_one_finding(self, tmp_path):
        """The id is derived from the silicon and the divergence, so recording
        it twice is caught rather than producing two records of one defect."""
        record(**GOOD, store=tmp_path)
        with pytest.raises(DisclosureError, match="already recorded"):
            record(**GOOD, store=tmp_path)

    def test_a_different_stepping_is_a_different_finding(self, tmp_path):
        record(**GOOD, store=tmp_path)
        other = record(**{**GOOD, "silicon": "6:151:5"}, store=tmp_path)

        assert len(load_all(tmp_path)) == 2
        assert other.id != load_all(tmp_path)[0].id


class TestTheEmbargoClock:
    def test_a_fresh_finding_is_not_due(self, tmp_path):
        record(**GOOD, store=tmp_path)

        assert due(within_days=14, store=tmp_path) == []

    def test_it_becomes_due_as_the_embargo_approaches(self, tmp_path):
        record(**GOOD, store=tmp_path)

        rows = due(within_days=400, store=tmp_path)
        assert len(rows) == 1

    def test_published_and_withdrawn_findings_leave_the_clock(self, tmp_path):
        f = record(**GOOD, store=tmp_path)
        set_status(f.id, "published", store=tmp_path)

        assert due(within_days=400, store=tmp_path) == []


class TestStatusAndDispute:
    def test_reporting_records_when(self, tmp_path):
        f = record(**GOOD, store=tmp_path)
        after = set_status(f.id, "reported", store=tmp_path)

        assert after.reported_at

    def test_a_dispute_is_recorded_alongside_not_escalated(self, tmp_path):
        """The PRD: record the dispute rather than escalating. `disputed` is a
        terminal state, not a failure."""
        f = record(**GOOD, store=tmp_path)
        after = set_status(f.id, "disputed",
                           dispute="vendor: documented in errata 81", store=tmp_path)

        assert after.status == "disputed"
        assert "errata 81" in after.dispute

    def test_withdrawn_is_a_status_not_a_deletion(self, tmp_path):
        """A finding that turns out to be our own bug must stay on record.
        Deleting it loses the evidence that the harness produces false
        positives, which is the number that decides whether to trust it."""
        f = record(**GOOD, store=tmp_path)
        set_status(f.id, "withdrawn", store=tmp_path)

        assert len(load_all(tmp_path)) == 1
        assert load_all(tmp_path)[0].status == "withdrawn"

    def test_an_unknown_status_is_refused(self, tmp_path):
        f = record(**GOOD, store=tmp_path)
        with pytest.raises(DisclosureError, match="status must be"):
            set_status(f.id, "probably fine", store=tmp_path)

    def test_every_status_in_the_policy_is_accepted(self, tmp_path):
        f = record(**GOOD, store=tmp_path)
        for state in STATUSES:
            set_status(f.id, state, store=tmp_path)


class TestContacts:
    def test_every_vendor_with_a_contact_has_an_embargo_default(self):
        import yaml

        data = yaml.safe_load(
            (ROOT / "agent" / "hardware" / "disclosure" / "contacts.yaml").read_text())
        for v in data["vendors"]:
            assert v["contact"]
            assert v.get("embargo_default_days", 90) > 0

    def test_no_credentials_are_stored(self):
        """Contacts are public record and stay that way."""
        text = (ROOT / "agent" / "hardware" / "disclosure" / "contacts.yaml").read_text()

        for secret in ("BEGIN PGP PRIVATE", "password", "api_key", "token:"):
            assert secret not in text
