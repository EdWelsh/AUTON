"""The conformance corpora and their verdicts (hardware-truth H10).

The corpora decide what "this chip is wrong" may mean, so the rules are tested:
every entry cites a clause, only `architectural` entries can fail a chip, and a
divergence carries its citation all the way to a disclosure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from conformance import (CorpusError, Divergence, bits, disclose,  # noqa: E402
                         load_corpus, report, summarise, write_operands)

CORPUS = ROOT / "agent" / "kernel_spec" / "conformance"


def test_every_shipped_entry_cites_a_clause():
    files = load_corpus(CORPUS)
    assert files, "no corpora"
    total = 0
    for name, _doc, entries in files:
        assert entries, f"{name} has no entries"
        for e in entries:
            assert e.clause.strip(), f"{name}:{e.id} has no clause"
            assert any(k in e.clause for k in ("SDM", "IEEE")), \
                f"{name}:{e.id} cites {e.clause!r}, which names no document"
            total += 1
    assert total >= 20


def test_an_entry_without_a_clause_is_refused(tmp_path):
    (tmp_path / "x.yaml").write_text(
        "operation: f64_div\nentries:\n  - id: x\n    class: semantic\n"
        "    guarantee: architectural\n    a: 1.0\n    b: 2.0\n")
    with pytest.raises(CorpusError, match="clause"):
        load_corpus(tmp_path)


def test_an_unknown_guarantee_is_refused(tmp_path):
    (tmp_path / "x.yaml").write_text(
        "operation: f64_div\nentries:\n  - id: x\n    clause: 'SDM 1'\n"
        "    class: semantic\n    guarantee: probably\n    a: 1.0\n    b: 2.0\n")
    with pytest.raises(CorpusError, match="guarantee"):
        load_corpus(tmp_path)


def test_a_duplicate_id_is_refused(tmp_path):
    (tmp_path / "x.yaml").write_text(
        "operation: f64_div\nentries:\n"
        "  - {id: x, clause: 'SDM 1', class: semantic, guarantee: architectural, a: 1.0, b: 2.0}\n"
        "  - {id: x, clause: 'SDM 2', class: semantic, guarantee: architectural, a: 1.0, b: 3.0}\n")
    with pytest.raises(CorpusError, match="duplicate"):
        load_corpus(tmp_path)


def test_the_fdiv_operands_are_the_historical_ones():
    """4195835 / 3145727, the pair that made this a famous question."""
    entry = next(e for _n, _d, es in load_corpus(CORPUS) for e in es
                 if e.id == "fp-div-fdiv-historical")
    assert float(entry.raw["a"]) == 4195835.0
    assert float(entry.raw["b"]) == 3145727.0
    assert bits(4195835.0) == 0x4150017EC0000000


def test_operands_are_written_as_bits_not_decimals(tmp_path):
    n_sem, n_fault = write_operands(tmp_path, CORPUS)
    assert n_sem >= 15 and n_fault >= 4
    ops = (tmp_path / "operands.txt").read_text()
    assert "4150017ec0000000" in ops, "the oracle must never parse a decimal"
    assert "4195835" not in ops
    faults = (tmp_path / "faults.txt").read_text()
    assert "ud-ud2 0f0b UD architectural" in faults


def test_zero_divergences_is_reported_as_a_finding():
    out = report(summarise("IDENTITY GenuineIntel x86_64\nOK fp-div-one-third 3fd5555555555555\n"))
    assert "0 divergence(s) across 1 clause-cited checks on GenuineIntel x86_64" in out
    assert "published as a finding" in out


def test_a_skip_says_so_rather_than_passing_quietly():
    out = report(summarise("SKIP semantic: not x86\nSUMMARY semantic checked=0 diverged=0"))
    assert "SKIPPED on this host" in out


def test_a_divergence_carries_its_clause():
    s = summarise("IDENTITY GenuineIntel part\n"
                  "DIVERGE fp-div-fdiv-historical got 3ff5575400000000 want 3ff557541c7c6b43\n")
    assert len(s.diverged) == 1
    d = s.diverged[0]
    assert d.expected == "3ff557541c7c6b43" and d.observed == "3ff5575400000000"
    assert "SDM" in d.clause or "IEEE" in d.clause
    assert "clause:" in report(s)


def test_a_model_specific_surprise_is_not_a_chip_defect():
    s = summarise("IDENTITY x\nNOT-ASSERTABLE ud-control-nop wanted none, faulted\n")
    assert not s.diverged
    assert "never a failure" in report(s)


def test_a_divergence_is_disclosed_with_its_citation(tmp_path):
    d = Divergence("fp-div-fdiv-historical", "Intel SDM Vol. 1 8.3.9 (FDIV)", "semantic",
                   "3ff557541c7c6b43", "3ff5575400000000")
    finding = disclose(d, "GenuineIntel 5:2:12 Pentium 60", store=tmp_path / "findings")
    assert finding.vendor == "intel"
    assert "FDIV" in finding.spec_citation
    assert finding.expected == "3ff557541c7c6b43"
    assert finding.silicon == "5:2:12", "the part, not the brand string"


def test_a_brand_string_alone_is_not_a_part(tmp_path):
    from disclosure import DisclosureError

    d = Divergence("x", "SDM 1", "semantic", "a", "b")
    with pytest.raises(DisclosureError, match="family:model:stepping"):
        disclose(d, "GenuineIntel 12th Gen Core i7", store=tmp_path / "findings")


def test_an_unknown_vendor_is_refused_rather_than_guessed(tmp_path):
    from disclosure import DisclosureError

    d = Divergence("x", "SDM 1", "semantic", "a", "b")
    with pytest.raises(DisclosureError, match="cannot tell the vendor"):
        disclose(d, "some unlabelled part", store=tmp_path / "findings")
