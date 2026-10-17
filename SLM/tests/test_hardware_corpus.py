"""The hardware reference corpus is generated from the tables, and says only what they say."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SLM" / "tools"))
sys.path.insert(0, str(ROOT / "agent" / "tools"))

import build_hardware_corpus as bhc  # noqa: E402

DATASET = ROOT / "SLM" / "datasets" / "hardware_reference.jsonl"


def _rows():
    return [json.loads(line) for line in DATASET.read_text().splitlines()]


def test_the_committed_corpus_is_what_the_tables_generate():
    assert _rows() == bhc.build(), "regenerate: python SLM/tools/build_hardware_corpus.py"


def test_every_vendor_answer_names_a_registry_id():
    reg = json.loads(bhc.REGISTRY.read_text())
    ids = {(i["scheme"], i["id"]) for e in reg["vendors"] for i in e["ids"]}
    for r in _rows():
        if r["fact"].startswith("registry:"):
            _, scheme, ident = r["fact"].split(":", 2)
            assert (scheme, ident) in ids
            assert ident in r["text"]


def test_known_silicon_answers():
    by_q = {r["text"]: r["response"] for r in _rows()}
    assert by_q["does haswell support fma4"].startswith("No")
    assert by_q["does znver1 support fma4"].startswith("No")
    assert by_q["does bdver1 support fma4"].startswith("Yes")
    assert by_q["does alderlake support avx512f"].startswith("Maybe")
    assert by_q["does pwr9 support 64bit-support"].startswith("Yes")
    assert by_q["does tt-ascalon-x support h"].startswith("Yes")
    assert by_q["does sifive-u74 support m"].startswith("Yes")


def test_no_feature_is_asked_that_no_processor_is_listed_with():
    """A feature on no processor (POWER's '64bit' mode flag, x86 rtm) would answer
    "No" for every part, including the ones that ship it."""
    import isa_tables

    tables = isa_tables.load_tables()
    asked = {tuple(r["fact"].split(":")[1:4:2]) for r in _rows() if r["fact"].startswith("isa:")}
    for arch, f in asked:
        assert any(f in v for v in tables[arch]["processors"].values()), (arch, f)
    assert ("powerpc", "64bit") not in asked and ("x86", "rtm") not in asked


def test_questions_are_unique_and_rows_are_kept_apart_from_chat():
    rows = _rows()
    assert len({r["text"] for r in rows}) == len(rows)
    assert all(r["caps"] == ["hardware-reference"] for r in rows)
