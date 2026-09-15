"""Fetch and normalise vendor documents.

The rule these exist to hold: **a record without provenance is refused.** An
erratum that cannot cite its document, revision and hash is a rumour, and a
table of rumours is worse than an empty table because it will be trusted.

Nothing here touches the network. `--from-file` ingests through the identical
path, so no test depends on a vendor's uptime.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from vendor_fetch import FetchError, Provenance, fetch  # noqa: E402
from vendor_ingest import (  # noqa: E402
    IngestError,
    Record,
    parse_ids_registry,
    write_derived,
)

SAMPLE_IDS = """\
#
#\tList of PCI IDs
#\tVersion: 2026.09.15
#
8086  Intel Corporation
\t100e  82540EM Gigabit Ethernet Controller
\t\t1028 0134  PowerEdge collectors
\t10d3  82574L Gigabit Network Connection
1af4  Red Hat, Inc.
\t1000  Virtio network device
"""


@pytest.fixture
def prov():
    return Provenance(
        vendor="pci-sig", document_id="pci-ids", title="pci.ids device registry",
        source="file:/tmp/pci.ids", retrieved_at="2026-09-15T00:00:00+00:00",
        sha256="a" * 64, bytes=len(SAMPLE_IDS), form="flat-text",
        redistributable=True, licence="GPL-2.0-or-later",
    )


class TestRegistryParsing:
    def test_devices_are_keyed_vendor_colon_device(self, prov):
        records = parse_ids_registry(SAMPLE_IDS, prov)

        assert {r.key for r in records} == {"8086:100e", "8086:10d3", "1af4:1000"}

    def test_the_vendor_name_is_carried_into_the_title(self, prov):
        records = parse_ids_registry(SAMPLE_IDS, prov)
        e1000 = next(r for r in records if r.key == "8086:100e")

        assert "Intel Corporation" in e1000.title
        assert "82540EM" in e1000.title

    def test_subsystem_entries_are_not_mistaken_for_devices(self, prov):
        """A doubly-indented line is a subsystem, not a device. Treating one as
        a device invents an id that is not on any bus."""
        records = parse_ids_registry(SAMPLE_IDS, prov)

        assert not [r for r in records if r.key.startswith("1028")]

    def test_the_document_revision_is_read_from_the_header(self, prov):
        records = parse_ids_registry(SAMPLE_IDS, prov)

        assert all(r.document_revision == "2026.09.15" for r in records)

    def test_every_record_carries_the_source_hash(self, prov):
        records = parse_ids_registry(SAMPLE_IDS, prov)

        assert all(r.sha256 == prov.sha256 for r in records)
        assert all(r.retrieved_at for r in records)


class TestProvenanceIsMandatory:
    def _record(self, **overrides):
        base = dict(kind="erratum", key="ADL001", title="Something",
                    vendor="intel", document_id="intel-spec-update",
                    document_revision="682436",
                    retrieved_at="2026-09-15T00:00:00+00:00", sha256="b" * 64)
        base.update(overrides)
        return Record(**base)

    @pytest.mark.parametrize("field", ["vendor", "document_id", "document_revision",
                                       "retrieved_at", "sha256"])
    def test_a_record_missing_any_provenance_field_is_refused(self, field):
        with pytest.raises(IngestError, match="lacks provenance"):
            self._record(**{field: ""}).validate()

    def test_the_refusal_names_the_missing_field(self):
        with pytest.raises(IngestError, match="sha256"):
            self._record(sha256="").validate()

    def test_a_record_without_a_title_is_refused(self):
        with pytest.raises(IngestError, match="no key or title"):
            self._record(title="").validate()

    def test_a_complete_record_validates(self):
        self._record().validate()

    def test_an_empty_derived_file_is_refused(self, tmp_path):
        """An empty file reads as 'nothing to report' when it means 'nothing
        was parsed'."""
        with pytest.raises(IngestError, match="empty derived file"):
            write_derived([], tmp_path)


class TestFetching:
    def test_network_fetching_says_so_rather_than_failing_obscurely(self):
        with pytest.raises(FetchError, match="network fetching is not implemented"):
            fetch("intel", "intel-sdm", from_file=None)

    def test_an_unknown_document_lists_what_the_vendor_has(self):
        with pytest.raises(FetchError, match="Available"):
            fetch("intel", "not-a-document", from_file="/dev/null")

    def test_a_vendor_with_no_documents_reports_its_gaps(self):
        """Apple publishes nothing; the error should say why rather than only
        that the id was not found."""
        with pytest.raises(FetchError, match="Gaps"):
            fetch("apple", "anything", from_file="/dev/null")

    def test_from_file_records_provenance(self, tmp_path):
        src = tmp_path / "pci.ids"
        src.write_text(SAMPLE_IDS)
        cache = tmp_path / "cache"

        prov = fetch("pci-sig", "pci-ids", from_file=str(src), cache=cache)

        assert prov.sha256 and len(prov.sha256) == 64
        assert prov.bytes == len(SAMPLE_IDS.encode())
        assert prov.retrieved_at.endswith("+00:00")
        assert (cache / "pci-sig" / "pci-ids" / "provenance.json").exists()

    def test_fetching_twice_is_idempotent(self, tmp_path):
        src = tmp_path / "pci.ids"
        src.write_text(SAMPLE_IDS)
        cache = tmp_path / "cache"

        first = fetch("pci-sig", "pci-ids", from_file=str(src), cache=cache)
        second = fetch("pci-sig", "pci-ids", from_file=str(src), cache=cache)

        assert first.sha256 == second.sha256
        assert first.retrieved_at == second.retrieved_at, "re-copied an unchanged document"

    def test_a_changed_document_is_re_recorded(self, tmp_path):
        src = tmp_path / "pci.ids"
        src.write_text(SAMPLE_IDS)
        cache = tmp_path / "cache"
        first = fetch("pci-sig", "pci-ids", from_file=str(src), cache=cache)

        src.write_text(SAMPLE_IDS + "1234  Some Vendor\n")
        second = fetch("pci-sig", "pci-ids", from_file=str(src), cache=cache)

        assert first.sha256 != second.sha256

    def test_a_missing_source_file_is_reported(self, tmp_path):
        with pytest.raises(FetchError, match="not a file"):
            fetch("pci-sig", "pci-ids", from_file=str(tmp_path / "absent"),
                  cache=tmp_path / "cache")

    def test_a_non_redistributable_document_cannot_be_cached_into_a_tracked_path(self, tmp_path):
        src = tmp_path / "sdm.pdf"
        src.write_bytes(b"%PDF-1.7\n")

        with pytest.raises(FetchError, match="not redistributable"):
            fetch("intel", "intel-sdm", from_file=str(src),
                  cache=ROOT / "agent" / "hardware")


class TestDerivedOutput:
    def test_derived_records_round_trip_as_jsonl(self, tmp_path, prov):
        records = parse_ids_registry(SAMPLE_IDS, prov)
        path = write_derived(records, tmp_path)

        lines = path.read_text().strip().splitlines()
        assert len(lines) == len(records)
        assert json.loads(lines[0])["sha256"] == prov.sha256
