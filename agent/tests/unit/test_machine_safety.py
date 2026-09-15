"""The mitigation registry and the "is this machine safe?" answer.

One property outweighs the rest: **unknown is never folded into safe.**

"No known issues" and "no knowledge" read identically in a summary and are
opposite statements. A machine for which nothing was ingested is unexamined,
not safe, and reporting otherwise is the most damaging thing this tool could
do — it is the exact answer a user acts on.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from errata_table import Identity  # noqa: E402
from machine_safety import SafetyReport, assess_machine  # noqa: E402
from mitigation_registry import (  # noqa: E402
    RegistryError,
    assess,
    load_all,
    load_one,
)

MITIGATIONS = ROOT / "agent" / "kernel_spec" / "mitigations"


@pytest.fixture(scope="module")
def registry():
    return load_all()


class TestTheRegistry:
    def test_it_loads_the_shipped_mitigations(self, registry):
        assert set(registry) == {"f00f-idt-remap", "fdiv-reference-check"}

    def test_the_two_entries_are_structurally_different(self, registry):
        """A registry proven only against fixable defects could not express the
        most important thing it can say."""
        f00f = registry["f00f-idt-remap"]
        fdiv = registry["fdiv-reference-check"]

        assert f00f.klass == "fault" and fdiv.klass == "semantic"
        assert f00f.status == "implementable"
        assert fdiv.status == "unmitigatable"

    def test_every_mitigation_states_a_cost(self, registry):
        """A mitigation with unstated cost gets applied everywhere. An image
        should be able to decline on cost, and cannot if nobody wrote it down."""
        for m in registry.values():
            assert m.cost.strip()

    def test_every_mitigation_states_how_to_verify_it(self, registry):
        """An image that claims a mitigation it did not apply is worse than one
        that declines it — the claim is the part a user acts on."""
        for m in registry.values():
            assert m.verify.strip()

    def test_every_mitigation_names_the_errata_it_addresses(self, registry):
        for m in registry.values():
            assert m.addresses


class TestRegistryValidation:
    def _write(self, tmp_path, name="probe", **overrides):
        fields = {
            "mitigation": name, "addresses": "[some-erratum]", "class": "fault",
            "requires": "[vmm]", "cost": "one page", "verify": "provoke it",
            "status": "implementable",
        }
        fields.update(overrides)
        lines = ["---"] + [f"{k}: {v}" for k, v in fields.items() if v is not None]
        lines += ["---", "", "# Probe", "", "Prose."]
        p = tmp_path / f"{name}.md"
        p.write_text("\n".join(lines))
        return p

    @pytest.mark.parametrize("field", ["mitigation", "addresses", "class",
                                       "cost", "verify", "status"])
    def test_a_missing_field_is_named(self, tmp_path, field):
        with pytest.raises(RegistryError, match=field):
            load_one(self._write(tmp_path, **{field: None}))

    def test_an_empty_cost_is_refused(self, tmp_path):
        with pytest.raises(RegistryError, match="cost"):
            load_one(self._write(tmp_path, cost=""))

    def test_an_unknown_class_is_refused_with_the_reason(self, tmp_path):
        with pytest.raises(RegistryError, match="verify differently"):
            load_one(self._write(tmp_path, **{"class": "vibes"}))

    def test_addressing_no_erratum_is_refused(self, tmp_path):
        with pytest.raises(RegistryError, match="change without a reason"):
            load_one(self._write(tmp_path, addresses="[]"))

    def test_a_filename_mismatch_is_refused(self, tmp_path):
        p = self._write(tmp_path, name="probe", mitigation="other")
        with pytest.raises(RegistryError, match="address the same thing"):
            load_one(p)


class TestTheFourCategories:
    def test_an_image_with_the_capability_can_mitigate(self, registry):
        a = assess(["intel-pentium-f00f"], {"vmm", "arch", "allocator"}, registry)

        assert a.counts()["mitigable"] == 1
        assert a.counts()["declined"] == 0

    def test_an_image_without_it_declines_rather_than_claiming_a_fix(self, registry):
        """The failure this exists to prevent: reporting a mitigation that was
        never applied."""
        a = assess(["intel-pentium-f00f"], {"arch", "allocator"}, registry)

        assert a.counts()["mitigable"] == 0
        assert a.counts()["declined"] == 1
        assert "lacks vmm" in a.declined[0][2]

    def test_an_unmitigatable_erratum_is_never_reported_as_mitigated(self, registry):
        """FDIV has no software fix. No capability set changes that."""
        for caps in ({"vmm", "arch", "allocator", "slm"}, set()):
            a = assess(["intel-pentium-fdiv"], caps, registry)
            assert a.counts()["unmitigatable"] == 1
            assert a.counts()["mitigable"] == 0

    def test_an_erratum_with_no_mitigation_is_reported_not_dropped(self, registry):
        """The registry's job includes saying what it cannot fix."""
        a = assess(["ADL001"], {"vmm", "arch", "allocator"}, registry)

        assert a.counts()["applicable"] == 1
        assert "no mitigation" in a.applicable[0][2]


class TestUnknownIsNeverSafe:
    def test_silicon_no_document_covers_is_reported_unexamined(self):
        report = assess_machine(Identity("AuthenticAMD", 25, 33, 0),
                                {"vmm", "arch", "allocator", "slm"})

        assert not report.examined
        assert "not the same as safe" in report.summary()

    def test_with_no_documents_at_all_it_says_so(self):
        report = assess_machine(Identity("GenuineIntel", 6, 151, 2),
                                {"vmm"}, documents=[])

        assert not report.examined
        assert "has not been examined" in report.summary()
        assert "safe" not in report.summary().replace("not the same as safe", "")

    def test_the_summary_never_claims_safe_without_examination(self):
        for identity in (Identity("AuthenticAMD", 25, 33, 0),
                         Identity("GenuineIntel", 6, 94, 3)):
            summary = assess_machine(identity, {"vmm"}).summary()
            lowered = summary.lower()
            if "not the same as safe" in lowered:
                continue
            assert "is safe" not in lowered, summary

    def test_the_report_names_what_it_consulted(self):
        """A reader must be able to see what the answer rests on. An errata list
        six months stale reads as current."""
        report = assess_machine(Identity("GenuineIntel", 6, 151, 2), {"vmm"})

        if report.documents:
            for d in report.documents:
                assert d["document"] and "errata" in d and "matched" in d


@pytest.mark.skipif(not (ROOT / ".cache" / "vendor" / "intel").is_dir(),
                    reason="no ingested Intel document")
class TestAgainstIngestedDocuments:
    def test_an_alder_lake_machine_gets_applicable_errata(self):
        report = assess_machine(Identity("GenuineIntel", 6, 151, 2),
                                {"vmm", "arch", "allocator", "slm"})

        assert report.examined
        assert report.assessment.counts()["applicable"] > 0

    def test_counts_and_not_applicable_account_for_every_erratum(self):
        """Every erratum lands in exactly one bucket. One that falls through a
        gap is one nobody is told about."""
        report = assess_machine(Identity("GenuineIntel", 6, 151, 2), {"vmm"})

        total = sum(d["errata"] for d in report.documents)
        counted = (sum(report.assessment.counts().values())
                   + len(report.unknown) + report.not_applicable)
        assert counted == total, f"{counted} accounted vs {total} errata"
