"""Identifying a PCI device from the ingested registry.

A model asked to name `8086:100e` produces something plausible, and plausible is
the whole problem: a phantom id with a driver decision attached cannot be told
apart from a real one downstream. The measured cost is in
`SLM/tools/build_corpus.py` — 14 corpus records carrying real-looking ids
produced 5 phantom citations per 50 novel turns, against 0 from a lookup.

So these tests are about the lookup staying a lookup, and about the third
outcome: a registry that was never read is a different state from a device that
is genuinely not listed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from device_registry import (  # noqa: E402
    Identification,
    Outcome,
    identify,
)

CACHED = identify("8086:100e").outcome is not Outcome.UNAVAILABLE
needs_registry = pytest.mark.skipif(not CACHED, reason="pci.ids not cached")


class TestAKnownDeviceIsNamedFromTheDocument:
    @needs_registry
    def test_a_known_device_identifies(self):
        ident = identify("8086:100e")

        assert ident.outcome is Outcome.IDENTIFIED
        assert "82540EM" in ident.title

    @needs_registry
    def test_the_identification_cites_its_document(self):
        """An answer that cannot say which revision of pci.ids it came from
        cannot be re-checked when the registry is updated."""
        ident = identify("8086:100e")

        assert ident.document_id == "pci-ids"
        assert ident.document_revision
        assert len(ident.sha256) == 64

    @needs_registry
    def test_case_and_whitespace_do_not_change_the_answer(self):
        assert identify(" 8086:100E ").title == identify("8086:100e").title

    @needs_registry
    def test_an_identification_is_truthy_only_when_identified(self):
        assert identify("8086:100e")
        assert not identify("ffff:ffff")


class TestNotListedIsNotTheSameAsNotChecked:
    @needs_registry
    def test_an_absent_device_is_unknown_not_empty(self):
        """An empty title reads as "no name", which a caller may render as a
        blank rather than as a refusal to guess."""
        ident = identify("ffff:ffff")

        assert ident.outcome is Outcome.UNKNOWN
        assert ident.reason
        assert ident.title == ""

    @needs_registry
    def test_unknown_still_cites_the_registry_it_read(self):
        """Knowing a device is absent is itself a fact from a document, and it
        goes stale the same way a positive identification does."""
        assert identify("ffff:ffff").document_revision

    def test_a_missing_registry_is_unavailable(self, monkeypatch):
        """The state on a fresh checkout: `.cache/vendor/` is gitignored.
        Collapsing this into UNKNOWN would report every device in the world as
        unlisted, and a build gate built on that would refuse every build."""
        import device_registry

        device_registry._index.cache_clear()
        monkeypatch.setattr(
            device_registry, "_index",
            lambda: (_ for _ in ()).throw(RuntimeError("no such file")))

        ident = device_registry.identify("8086:100e")

        assert ident.outcome is Outcome.UNAVAILABLE
        assert ident.outcome is not Outcome.UNKNOWN

    def test_unavailable_says_how_to_populate_the_cache(self, monkeypatch):
        import device_registry

        device_registry._index.cache_clear()
        monkeypatch.setattr(
            device_registry, "_index",
            lambda: (_ for _ in ()).throw(RuntimeError("no such file")))

        assert "vendor_fetch" in device_registry.identify("8086:100e").reason


class TestTheThreeOutcomesAreDistinct:
    def test_no_outcome_is_a_bare_boolean(self):
        """When "cannot tell" is possible it is a value, not a missing answer —
        the same rule `errata_table.Verdict` follows."""
        assert len(set(Outcome)) == 3

    @needs_registry
    def test_describe_never_invents_a_name(self):
        for bad in ("ffff:ffff", "0000:0000"):
            ident = identify(bad)
            if ident.outcome is Outcome.UNKNOWN:
                assert "not listed" in ident.describe()
