"""errata.bin (hardware-truth H13): precomputed verdicts keyed by silicon."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SLM" / "tools"))
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from errata_format import ErrataFormatError, Key, Rec, pack, unpack  # noqa: E402

T = {Key(1, 6, 151, 2): [Rec("ADL001: X87 FDP", 1, 1, 0, 14), Rec("ADL002: y", 0, 2, 0, 15)],
     Key(2, 25, 33, 0): [Rec("AMD1: z", 2, 3, 1, 0)]}
DOCS = [("intel/x", "682436"), ("amd/y", "1")]


def test_round_trip():
    docs, table = unpack(pack(DOCS, T))
    assert docs == DOCS and table == T


def test_keys_are_sorted_for_binary_search():
    data = pack(DOCS, {Key(2, 25, 33, 0): T[Key(2, 25, 33, 0)], Key(1, 6, 151, 2): T[Key(1, 6, 151, 2)]})
    assert list(unpack(data)[1]) == [Key(1, 6, 151, 2), Key(2, 25, 33, 0)]


def test_shared_text_is_stored_once():
    same = {Key(1, 6, 151, 2): [Rec("A: t", 1, 1, 0, 1)], Key(1, 6, 151, 5): [Rec("A: t", 1, 1, 0, 1)]}
    assert pack(DOCS, same).count(b"A: t\0") == 1


@pytest.mark.parametrize("cut", [0, 5, 11, 30, -1])
def test_truncation_is_refused(cut):
    data = pack(DOCS, T)
    with pytest.raises(ErrataFormatError):
        unpack(data[:cut if cut >= 0 else len(data) - 1])


def test_an_empty_module_is_valid_and_means_not_examined():
    docs, table = unpack(pack([], {}))
    assert docs == [] and table == {}


def _cached() -> bool:
    from build_errata_table import documents
    from vendor_ingest import CACHE
    return bool(documents(CACHE))


needs_doc = pytest.mark.skipif(not _cached(), reason="no ingested errata document")


@needs_doc
def test_built_from_the_ingested_document():
    from build_errata_table import build
    from vendor_ingest import CACHE

    docs, table = build(CACHE)
    assert ("intel/intel-spec-update", "682436") in docs
    assert all(len(v) == 94 for v in table.values())
    assert Key(1, 6, 151, 2) in table


@needs_doc
def test_scoped_to_a_target_silicon_ships_one_key():
    from build_errata_table import build
    from vendor_ingest import CACHE

    _, table = build(CACHE, {"vendor": "GenuineIntel", "family": 6, "model": 151, "stepping": 2})
    assert list(table) == [Key(1, 6, 151, 2)]


@needs_doc
def test_silicon_no_document_covers_ships_nothing():
    from build_errata_table import build
    from vendor_ingest import CACHE

    _, table = build(CACHE, {"vendor": "GenuineIntel", "family": 6, "model": 85, "stepping": 4})
    assert table == {}
