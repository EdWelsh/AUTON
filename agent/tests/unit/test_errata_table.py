"""Errata lookup for a captured silicon identity.

The rule these hold: **never answer NO when the truth is "I cannot tell".**
Reporting a vulnerable machine as safe is the failure the hardware-truth PRD
exists to avoid, and reporting a safe one as vulnerable destroys trust in every
other answer. So the verdict is three-valued and always carries a reason.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from errata_table import (  # noqa: E402
    ErrataTable,
    Identity,
    Signature,
    Verdict,
    _match_column,
)


@dataclass
class FakeErratum:
    key: str
    applies_to: list = field(default_factory=list)
    document_id: str = "intel-spec-update"


def table(signatures, *errata):
    return ErrataTable(records=list(errata), signatures=list(signatures))


ADL = [
    Signature.from_cpuid(0x90672, ("ADL-HX", "ADL-S")),
    Signature.from_cpuid(0x906A3, ("ADL-H", "ADL-P")),
    Signature.from_cpuid(0x906A4, ("ADL-U15W", "ADL-U9W")),
]


class TestSignatureFolding:
    def test_a_documented_signature_folds_to_the_documented_part(self):
        """0x90672 is Intel's own stated Alder Lake-S signature. It must fold to
        family 6 model 151 — the same value tests/kernel/identity_test.c pins,
        derived independently from the vendor's identification table."""
        s = Signature.from_cpuid(0x90672, ())

        assert (s.family, s.model, s.stepping) == (6, 151, 2)

    def test_the_mobile_signature_folds_to_a_different_model(self):
        s = Signature.from_cpuid(0x906A3, ())

        assert (s.family, s.model, s.stepping) == (6, 154, 3)


class TestColumnMatching:
    def test_a_line_matches_its_own_column(self):
        assert _match_column(["ADL-S"], {"S": "No Fix"}) == ("S", "No Fix")

    def test_a_shared_column_matches_either_line(self):
        """The errata table heads one column `H/P` because two lines share it."""
        assert _match_column(["ADL-H"], {"H/P": "Fixed"}) == ("H/P", "Fixed")
        assert _match_column(["ADL-P"], {"H/P": "Fixed"}) == ("H/P", "Fixed")

    def test_a_longer_line_name_matches_its_column_prefix(self):
        """`ADL-U15W` belongs under a column headed simply `U`."""
        assert _match_column(["ADL-U15W"], {"U": "No Fix"}) == ("U", "No Fix")

    def test_an_exact_match_beats_a_prefix_match(self):
        """`ADL-HX` must land in `HX`, not in `H/P` — both match on prefix."""
        got = _match_column(["ADL-HX"], {"H/P": "Fixed", "HX": "No Fix"})

        assert got == ("HX", "No Fix")

    def test_no_match_returns_none(self):
        assert _match_column(["ADL-S"], {"Q": "No Fix"}) is None


class TestVerdicts:
    def test_a_matched_line_decides(self):
        t = table(ADL, FakeErratum("ADL001", [{"line": "S", "status": "No Fix"}]))

        a = t.applies(Identity("GenuineIntel", 6, 151, 2), t.records[0])

        assert a.verdict is Verdict.APPLIES
        assert "S" in a.reason

    def test_fixed_means_not_applicable(self):
        t = table(ADL, FakeErratum("ADL010", [{"line": "S", "status": "Fixed"}]))

        assert t.applies(Identity("GenuineIntel", 6, 151, 2),
                         t.records[0]).verdict is Verdict.NOT_APPLICABLE

    def test_silicon_the_document_does_not_cover_is_not_applicable(self):
        """A confident NO, not an absence: the document states which parts it
        describes, and this is not one."""
        t = table(ADL, FakeErratum("ADL001", [{"line": "S", "status": "No Fix"}]))

        a = t.applies(Identity("GenuineIntel", 6, 94, 3), t.records[0])

        assert a.verdict is Verdict.NOT_APPLICABLE
        assert "no processor" in a.reason

    def test_every_line_agreeing_makes_the_line_irrelevant(self):
        """If the status is the same on every line, the answer holds whichever
        line this part is — so it can be given without resolving the line."""
        t = table([], FakeErratum("X1", [
            {"line": "S", "status": "No Fix"}, {"line": "U", "status": "No Fix"}]))

        a = t.applies(Identity("GenuineIntel", 6, 151, 2), t.records[0])

        assert a.verdict is Verdict.APPLIES
        assert "every processor line agrees" in a.reason


class TestNeverGuess:
    def test_disagreeing_lines_with_an_unresolved_identity_is_unknown(self):
        t = table([], FakeErratum("X2", [
            {"line": "S", "status": "No Fix"}, {"line": "U", "status": "Fixed"}]))

        a = t.applies(Identity("GenuineIntel", 6, 151, 2), t.records[0])

        assert a.verdict is Verdict.UNKNOWN
        assert "false statement" in a.reason

    def test_a_record_without_applicability_is_unknown_not_no(self):
        t = table(ADL, FakeErratum("X3", []))

        assert t.applies(Identity("GenuineIntel", 6, 151, 2),
                         t.records[0]).verdict is Verdict.UNKNOWN

    def test_no_signature_data_never_produces_a_confident_no(self):
        """With no identification table parsed, 'this document does not cover
        your silicon' is unsupportable — and answering NO there would report
        every erratum as inapplicable to every machine."""
        t = table([], FakeErratum("X4", [{"line": "S", "status": "No Fix"}]))

        a = t.applies(Identity("GenuineIntel", 6, 999, 0), t.records[0])

        assert a.verdict is not Verdict.NOT_APPLICABLE

    def test_every_answer_carries_a_reason(self):
        t = table(ADL,
                  FakeErratum("A", [{"line": "S", "status": "No Fix"}]),
                  FakeErratum("B", []),
                  FakeErratum("C", [{"line": "S", "status": "No Fix"},
                                    {"line": "U", "status": "Fixed"}]))

        for answer in t.query(Identity("GenuineIntel", 6, 151, 2)):
            assert answer.reason.strip()


class TestMicrocode:
    """No document ingested so far uses "Plan Fix" — both Intel updates carry
    only No Fix / Fixed / N/A. The path is exercised synthetically, because a
    branch that has never run is not known to work."""

    def test_plan_fix_with_an_unread_microcode_revision_is_unknown(self):
        t = table(ADL, FakeErratum("P1", [{"line": "S", "status": "Plan Fix"}]))

        a = t.applies(Identity("GenuineIntel", 6, 151, 2, microcode_rev=None),
                      t.records[0])

        assert a.verdict is Verdict.UNKNOWN
        assert "microcode revision was not read" in a.reason

    def test_plan_fix_with_a_known_revision_is_still_unknown_but_says_why(self):
        """Knowing the revision is not enough without the revision guidance
        document to compare it against. The reason must distinguish the two."""
        t = table(ADL, FakeErratum("P2", [{"line": "S", "status": "Plan Fix"}]))

        a = t.applies(Identity("GenuineIntel", 6, 151, 2, microcode_rev=0x429),
                      t.records[0])

        assert a.verdict is Verdict.UNKNOWN
        assert "0x429" in a.reason
        assert "revision guidance" in a.reason

    def test_no_fix_is_independent_of_microcode(self):
        """Intel: "There are no plans to fix this erratum." Microcode cannot
        change that, so the verdict must not become UNKNOWN when it is unread."""
        t = table(ADL, FakeErratum("N1", [{"line": "S", "status": "No Fix"}]))

        a = t.applies(Identity("GenuineIntel", 6, 151, 2, microcode_rev=None),
                      t.records[0])

        assert a.verdict is Verdict.APPLIES
        assert "microcode state is irrelevant" in a.reason


@pytest.mark.skipif(
    not (ROOT / ".cache" / "vendor" / "intel").is_dir(),
    reason="no cached Intel document",
)
class TestAgainstRealDocuments:
    def test_alder_lake_matches_adl_errata(self):
        from errata_table import load

        t = load(ROOT / ".cache" / "vendor" / "intel-682436.pdf")
        answers = t.query(Identity("GenuineIntel", 6, 151, 2))

        assert len(answers) > 80
        assert any(a.verdict is Verdict.APPLIES for a in answers)
        assert all("exact CPUID signature" in a.reason for a in answers[:5])

    def test_alder_lake_does_not_match_a_kaby_lake_document(self):
        from errata_table import load

        t = load(ROOT / ".cache" / "vendor" / "intel-334663.pdf")
        answers = t.query(Identity("GenuineIntel", 6, 151, 2))

        assert all(a.verdict is Verdict.NOT_APPLICABLE for a in answers)
