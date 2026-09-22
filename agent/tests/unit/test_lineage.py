"""Errata lineage and retrodiction (H9), on synthetic generations.

The real lineage needs 8 ingested spec updates a person downloads; these prove
the linking, classing and scoring before any number is quoted from them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from lineage import Erratum, LineageError, classify, link, load_classes, score  # noqa: E402
from retrodict import carry_score, classes_score  # noqa: E402

X87 = "X87 FDP Value May be Saved Incorrectly"
X87_DETAIL = "Execution of FSAVE FNSAVE FSTENV may save an incorrect FDP value"


def e(gen, key, title, detail="", status="No Fix"):
    return Erratum(f"intel/g{gen}", gen, key, title, detail, status, 1)


def docs(*errata):
    out = {}
    for x in errata:
        out.setdefault(x.document, []).append(x)
    return out


def test_one_document_is_not_a_lineage():
    with pytest.raises(LineageError, match="one document is not a lineage"):
        link(docs(e(12, "ADL001", X87)))


def test_a_carried_erratum_links_across_generations_under_new_ids():
    d = docs(e(10, "CML001", X87, X87_DETAIL), e(11, "RKL004", "X87 FDP Value Might Be Saved Incorrectly", X87_DETAIL),
             e(12, "ADL001", X87, X87_DETAIL), e(12, "ADL002", "USB Port Does Not Send LFPS Burst"))
    chains = link(d)
    recurring = [c for c in chains if len(c.generations) > 1]
    assert len(recurring) == 1
    assert recurring[0].generations == [10, 11, 12]
    assert {m.key for m in recurring[0].members} == {"CML001", "RKL004", "ADL001"}


def test_hedges_do_not_make_different_errata_similar():
    a = e(11, "A", "Processor May Hang if Warm Reset Triggers During BIOS Initialization")
    b = e(12, "B", "Performance Monitoring Event May Undercount")
    assert score(a, b) < 0.2


def test_every_link_is_cited():
    chains = link(docs(e(11, "RKL004", X87, X87_DETAIL), e(12, "ADL001", X87, X87_DETAIL)))
    cite = next(c for c in chains if len(c.members) == 2).members[0].cite()
    assert set(cite) == {"document", "generation", "id", "title", "page"}


def test_classes_from_keywords_and_overrides():
    classes = load_classes()
    assert classify(e(12, "ADL038", "OFFCORE_REQUESTS_OUTSTANDING Performance Monitoring Events May be Inaccurate"), classes) == "performance-monitoring"
    assert classify(e(12, "ADL020", "VMX-Preemption Timer May Not Work if Configured With a Value of 1"), classes) == "virtualisation"
    assert classify(e(12, "ADL999", "Something Nobody Categorised"), classes) == "other"
    classes = {**classes, "overrides": {"intel/g12/ADL999": "debug-trace"}}
    assert classify(e(12, "ADL999", "Something Nobody Categorised"), classes) == "debug-trace"


def _three_generations():
    return docs(
        e(10, "C1", X87, X87_DETAIL), e(10, "C2", "Performance Monitoring Event May Overcount"),
        e(11, "R1", X87, X87_DETAIL), e(11, "R2", "Performance Monitoring Event May Overcount"),
        e(11, "R3", "PCIe Link May Fail to Train", status="Fixed"),
        e(12, "A1", X87, X87_DETAIL), e(12, "A2", "xHCI Controller Hang With Zero-Length Packet"))


def test_class_retrodiction_scores_against_what_was_published():
    lin, base = classes_score(_three_generations(), 12, load_classes())
    # predicted: classes in >= 2 of gens 10-11: instruction-behaviour, performance-monitoring
    assert (lin.predicted, lin.actual, lin.hit) == (2, 2, 1)
    # the baseline (every class seen before) includes io-pcie-usb from gen 11's
    # PCIe erratum, which gen 12's xHCI hang shares: here guessing beats lineage.
    assert (base.predicted, base.hit) == (3, 2)
    assert base.recall > lin.recall


def test_carry_over_prediction_skips_what_was_fixed():
    lin, base = carry_score(_three_generations(), 12)
    # gen 11: R1 recurs as A1; R2 does not; R3 was Fixed
    assert (lin.predicted, lin.actual, lin.hit) == (2, 1, 1)
    assert (base.predicted, base.hit) == (3, 1)
    assert lin.precision > base.precision


def test_retrodiction_refuses_without_two_earlier_generations():
    with pytest.raises(LineageError):
        carry_score(docs(e(11, "R1", X87), e(12, "A1", X87)), 12)
    with pytest.raises(LineageError, match="not ingested"):
        carry_score(_three_generations(), 13)
