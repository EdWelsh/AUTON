"""Joining a target's silicon to the errata table.

`machine_safety.py` could already answer "is this machine safe to run this image
on" — it just had nothing to ask about, because until D1 no file in the tree
recorded a machine's identity in a reviewable form.

The case this phase is really about is the one that looks like success.
`firecracker.md` records `vendor: unknown, family: 0, source: assumed`, because a
microVM guest inherits the host CPU and cannot read it. Handed to
`assess_machine` as-is that yields "nothing applies" — a clean bill of health for
silicon nobody has identified.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from errata_join import join, silicon_identity  # noqa: E402
from errata_table import Identity  # noqa: E402
from target_spec import load  # noqa: E402

TARGETS = ROOT / "agent" / "kernel_spec" / "targets"

# A signature the ingested Intel document actually covers, so the applicable
# path is exercised rather than assumed.
COVERED = ("6", "151", "2")


@pytest.fixture
def target_file(tmp_path):
    def _write(name="widget", silicon=None, klass="bare-metal", platform=None):
        sil = silicon or {"vendor": "GenuineIntel", "family": COVERED[0],
                          "model": COVERED[1], "stepping": COVERED[2],
                          "source": "probed"}
        lines = ["---", f"target: {name}", f"class: {klass}", "arch: x86_64",
                 "firmware: uefi", "silicon:"]
        lines += [f"  {k}: {v}" for k, v in sil.items()]
        if platform:
            lines.append("platform:")
            lines += [f"  {k}: {v}" for k, v in platform.items()]
        lines += ["devices:", '  - id: "8086:100e"', "    role: network",
                  "    source: probed",
                  "provenance:", "  stated_by: test", "---", "", "# W", ""]
        path = tmp_path / f"{name}.md"
        path.write_text("\n".join(lines))
        return load(path)
    return _write


class TestSiliconToIdentity:
    def test_a_probed_target_yields_an_identity(self):
        ident = silicon_identity(load(TARGETS / "qemu-pc.md"))

        assert isinstance(ident, Identity)
        assert ident.vendor == "GenuineIntel"
        assert ident.family == 6

    def test_assumed_silicon_yields_none_not_a_zeroed_identity(self):
        """`Identity("unknown", 0, 0, 0)` is a valid object that assess_machine
        will happily answer about, and the answer will be "nothing applies". A
        missing return value cannot be mistaken for an answer; a zeroed one can."""
        assert silicon_identity(load(TARGETS / "firecracker.md")) is None

    def test_assumed_silicon_with_plausible_values_still_yields_none(self, target_file):
        """The case `firecracker.md` does not cover: someone assumed a specific
        part rather than leaving it unknown. `vendor: unknown` masks the
        assumed-source check on that file, so without this test the check looks
        redundant and can be deleted — D5's elicitation will produce exactly
        this shape, a confident-looking guess.
        """
        t = target_file(silicon={"vendor": "GenuineIntel", "family": COVERED[0],
                                 "model": COVERED[1], "stepping": COVERED[2],
                                 "source": "assumed"})

        assert silicon_identity(t) is None

    def test_that_target_is_reported_unknown_not_assessed(self, target_file):
        t = target_file(silicon={"vendor": "GenuineIntel", "family": COVERED[0],
                                 "model": COVERED[1], "stepping": COVERED[2],
                                 "source": "assumed"})

        r = join(t, {"boot"})

        assert r.unknown_because
        assert r.report is None
        assert "safe" not in r.summary().lower()

    def test_a_non_numeric_family_yields_none(self, target_file):
        """Never int()-with-a-fallback: a non-numeric family becoming 0 is the
        zeroed-Identity problem wearing a different hat."""
        t = target_file(silicon={"vendor": "GenuineIntel", "family": "six",
                                 "model": "151", "stepping": "2",
                                 "source": "probed"})

        assert silicon_identity(t) is None

    def test_an_unknown_vendor_yields_none(self, target_file):
        t = target_file(silicon={"vendor": "unknown", "family": "6",
                                 "model": "151", "stepping": "2",
                                 "source": "probed"})

        assert silicon_identity(t) is None

    def test_the_string_fields_are_converted_not_passed_through(self):
        """The target stores strings; `Identity` wants ints. A string family
        would compare unequal to every signature and report nothing applies."""
        ident = silicon_identity(load(TARGETS / "qemu-pc.md"))

        assert isinstance(ident.family, int)
        assert isinstance(ident.model, int)


class TestAssumedSiliconIsNeverACleanBill:
    def test_firecracker_is_unknown(self):
        r = join(load(TARGETS / "firecracker.md"), {"boot"})

        assert r.unknown_because
        assert not r.examined

    def test_the_reason_names_silicon(self):
        r = join(load(TARGETS / "firecracker.md"), {"boot"})
        assert "silicon" in r.unknown_because

    def test_the_word_safe_never_appears(self):
        """machine_safety.py's own rule, applied one level up: "this machine has
        not been examined — that is not the same as safe"."""
        r = join(load(TARGETS / "firecracker.md"), {"boot"})

        assert "safe" not in r.summary().lower()

    def test_the_table_is_not_even_queried(self, target_file):
        """Querying it would produce a verdict, and any verdict about silicon
        nobody identified is a false statement."""
        t = target_file(silicon={"vendor": "unknown", "family": "0",
                                 "model": "0", "stepping": "0",
                                 "source": "assumed"})

        assert join(t, {"boot"}).report is None


class TestCoveredSiliconIsAssessed:
    def test_an_applicable_erratum_is_reported(self, target_file):
        r = join(target_file(), {"boot", "allocator"})

        if not r.examined or not r.report.documents:
            pytest.skip("no errata documents cached")
        assert r.report.assessment.counts()["applicable"] > 0

    def test_uncovered_silicon_says_it_was_not_examined(self):
        """QEMU's default CPU is family 6 model 6 — no ingested document covers
        it, and that is reported as unexamined rather than as clear."""
        r = join(load(TARGETS / "qemu-pc.md"), {"boot"})

        if not r.report or not r.report.documents:
            pytest.skip("no errata documents cached")
        assert "not been examined" in r.summary()
        assert "that is not the same as safe" in r.summary()


class TestTheRefusalIsNarrow:
    def test_applicable_errata_alone_do_not_block(self, target_file):
        """On real hardware that is most of an Intel specification update.
        Refusing there would make the tool unusable."""
        r = join(target_file(), {"boot", "allocator"})

        if not r.examined:
            pytest.skip("no verdict could be reached for this target")
        # `examined` says a verdict was reachable, not that there was anything
        # to reach it from. The errata corpus lives under a gitignored cache, so
        # on a fresh clone every count is zero and this asserted 0 > 0 — the
        # guard and its own skip reason disagreed, and CI was the first checkout
        # to notice.
        if not any(r.report.assessment.counts().values()):
            pytest.skip("no errata documents cached, so there is nothing to apply")
        assert r.report.assessment.counts()["applicable"] > 0
        assert r.blocking == []

    def test_only_an_explicit_unmitigatable_blocks(self, target_file, monkeypatch):
        """`status: unmitigatable` is a human judgement someone wrote down, not
        an inference. An image on silicon that will compute wrong answers with
        no recourse is worth stopping."""
        import errata_join
        from mitigation_registry import Assessment

        class _Report:
            assessment = Assessment(unmitigatable=[("X1", None, "no fix")])
            documents = [{"document": "d", "errata": 1, "matched": True,
                          "signatures": 1}]
            unknown: list = []
            not_applicable = 0

            def summary(self):
                return "one unmitigatable erratum"

        monkeypatch.setattr(errata_join, "assess_machine",
                            lambda *a, **k: _Report())
        r = errata_join.join(target_file(), {"boot"})

        assert r.blocking == ["X1"]

    def test_an_unknown_verdict_neither_blocks_nor_counts_as_clear(self, target_file, monkeypatch):
        import errata_join
        from mitigation_registry import Assessment

        class _Report:
            assessment = Assessment()
            documents = [{"document": "d", "errata": 1, "matched": True,
                          "signatures": 1}]
            unknown = [("X9", "disagreeing lines")]
            not_applicable = 0

            def summary(self):
                return "nothing applicable"

        monkeypatch.setattr(errata_join, "assess_machine",
                            lambda *a, **k: _Report())
        r = errata_join.join(target_file(), {"boot"})

        assert r.blocking == []
        assert r.report.unknown == [("X9", "disagreeing lines")]
        assert r.report.not_applicable == 0


class TestErrataInheritanceIsRecordedNotAssumed:
    def test_a_hosted_guest_carries_the_open_question(self, target_file):
        """PRD open question 4. A silent absence here would read as "no"."""
        t = target_file(klass="auton-hosted",
                        platform={"host_image": "abc123def456", "source": "derived"})

        assert "INHERITANCE" in join(t, {"boot"}).inheritance

    def test_it_says_the_question_is_open(self, target_file):
        t = target_file(klass="auton-hosted",
                        platform={"host_image": "abc123def456", "source": "derived"})

        note = join(t, {"boot"}).inheritance
        assert "unanswered" in note
        assert "would read as 'no'" in note

    def test_a_non_hosted_target_carries_no_such_note(self, target_file):
        assert join(target_file(), {"boot"}).inheritance == ""


class TestThePackageCarriesTheReport:
    def test_packaging_writes_an_errata_report(self, tmp_path, target_file):
        import json

        from package_image import package

        t = target_file(name="covered")
        out = tmp_path / "out"
        package("what hardware is this", out, ROOT / "kernels" / "x86_64",
                target=t.path)

        record = json.loads((out / "spec" / "errata.json").read_text())
        assert record["target"] == "covered"
        assert "summary" in record

    def test_the_report_names_the_documents_consulted(self, tmp_path, target_file):
        import json

        from package_image import package

        t = target_file(name="covered")
        out = tmp_path / "out"
        package("what hardware is this", out, ROOT / "kernels" / "x86_64",
                target=t.path)

        record = json.loads((out / "spec" / "errata.json").read_text())
        if not record.get("documents"):
            pytest.skip("no errata documents cached")
        assert record["documents"][0]["document"]

    def test_unknown_errata_are_kept_separate_from_not_applicable(self, tmp_path, target_file):
        """Merging them into a total is how an unknown becomes a clear."""
        import json

        from package_image import package

        t = target_file(name="covered")
        out = tmp_path / "out"
        package("what hardware is this", out, ROOT / "kernels" / "x86_64",
                target=t.path)

        record = json.loads((out / "spec" / "errata.json").read_text())
        assert "unknown_errata" in record
        assert "not_applicable" in record

    def test_a_package_with_no_target_has_no_errata_record(self, tmp_path):
        from package_image import package

        out = tmp_path / "out"
        pkg = package("what hardware is this", out, ROOT / "kernels" / "x86_64")

        assert pkg.errata == {}
        assert not (out / "spec" / "errata.json").exists()
