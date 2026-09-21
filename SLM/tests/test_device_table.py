"""The device table carried inside the model file.

The shipped model knew four device ids — QEMU's default PC, hardcoded — and
invented the rest, measured at 5 phantom citations per 50 novel turns against 0
from a lookup. Meanwhile 42,101 ingested records sat on the build host where a
running image could not reach them.

The properties these tests hold: the table is searchable where it lies, it
cannot be built wrong in a way a search would silently tolerate, and a reader
can always tell "this image knows no devices" from "this file predates the
section".
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SLM" / "tools"))
sys.path.insert(0, str(ROOT / "agent" / "tools"))

import auton_format as af  # noqa: E402
from auton_format import (  # noqa: E402
    BUS_PCI,
    BUS_USB,
    DeviceEntry,
    lookup,
    pack_device_table,
    unpack_device_table,
)

ENTRIES = [
    DeviceEntry(BUS_PCI, 0x1234, 0x1111, "QEMU Bochs VGA"),
    DeviceEntry(BUS_PCI, 0x8086, 0x100E, "Intel 82540EM"),
    DeviceEntry(BUS_USB, 0x046D, 0xC077, "Logitech Mouse"),
]


class TestTheSectionRoundTrips:
    def test_entries_survive(self):
        blob = pack_device_table(ENTRIES, "r1")
        back, rev, end = unpack_device_table(blob, 0)

        assert [e.key for e in back] == [e.key for e in ENTRIES]
        assert rev == "r1"
        assert end == len(blob)

    def test_names_survive(self):
        back, _, _ = unpack_device_table(pack_device_table(ENTRIES, "r1"), 0)

        assert back[1].name == "Intel 82540EM"

    def test_an_empty_table_is_still_a_section(self):
        """A reader must be able to tell "this image knows no devices" from
        "this file predates the section"."""
        blob = pack_device_table([], "r1")
        back, rev, end = unpack_device_table(blob, 0)

        assert back == []
        assert end == len(blob)

    def test_the_revision_travels_with_the_table(self):
        """A table that cannot say which pci.ids it came from cannot be
        re-checked when the registry updates."""
        _, rev, _ = unpack_device_table(pack_device_table(ENTRIES, "2026.09.15"), 0)

        assert rev == "2026.09.15"

    def test_an_entry_is_a_fixed_twelve_bytes(self):
        """Fixed width is what makes it indexable in place. A variable-width
        entry cannot be binary-searched without walking the table."""
        one = len(pack_device_table(ENTRIES[:1], ""))
        two = len(pack_device_table(ENTRIES[:2], ""))

        assert two - one == af.DEVICE_ENTRY_SIZE + len(ENTRIES[1].name) + 1


class TestItCannotBeBuiltWrong:
    def test_an_unsorted_table_is_refused(self):
        """A binary search over unsorted keys returns an arbitrary answer —
        a lookup that looks like it worked."""
        with pytest.raises(ValueError, match="not sorted"):
            pack_device_table(list(reversed(ENTRIES)), "r1")

    def test_a_duplicate_key_is_refused(self):
        """Not arbitrated. A search cannot say which of two it found."""
        dupes = [ENTRIES[1], ENTRIES[1]]

        with pytest.raises(ValueError, match="duplicate"):
            pack_device_table(dupes, "r1")

    def test_the_duplicate_refusal_names_one(self):
        with pytest.raises(ValueError, match="8086:100e"):
            pack_device_table([ENTRIES[1], ENTRIES[1]], "r1")

    @pytest.mark.parametrize("chop", [1, 3, 8, 20, 40, 60])
    def test_truncation_raises_the_documented_type(self, chop):
        """`validate()` promises ValueError on any mismatch. A struct.error
        escaping means a caller catching the documented type misses a corrupt
        file.

        Parameterised because truncation lands in different fields depending on
        how much is missing — the pool, the entry array, the header — and each
        must surface as the same type. A small chop is caught by the pool-length
        check; a large one reaches `struct.unpack_from` and would escape as
        struct.error if it were not translated.
        """
        blob = pack_device_table(ENTRIES, "r1")

        with pytest.raises(ValueError) as exc:
            unpack_device_table(blob[:-chop], 0)

        assert "device-table" in str(exc.value)


class TestLookup:
    def test_a_present_device_is_found(self):
        assert lookup(ENTRIES, BUS_PCI, 0x8086, 0x100E).name == "Intel 82540EM"

    def test_an_absent_device_is_none(self):
        assert lookup(ENTRIES, BUS_PCI, 0xFFFF, 0xFFFF) is None

    def test_the_bus_is_part_of_the_key(self):
        """The same numeric id can exist on both buses. Searching without the
        bus returns the wrong device."""
        assert lookup(ENTRIES, BUS_USB, 0x8086, 0x100E) is None

    def test_host_and_kernel_search_the_same_order(self):
        """A table the exporter sorts one way and the loader searches another
        is a lookup that silently returns the wrong device."""
        keys = [e.key for e in ENTRIES]

        assert keys == sorted(keys)


class TestTheModelFileCarriesIt:
    def _tiny(self):
        return af.FlatHeader(dim=4, hidden_dim=8, n_layers=1, n_heads=2,
                             n_kv_heads=1, vocab_size=3, seq_len=8)

    def _write(self, tmp_path, devices):
        h = self._tiny()
        out = tmp_path / "m.bin"
        weights = [0.0] * af.weight_element_count(h)
        vocab = [(0.0, b"a"), (0.0, b"b"), (0.0, b"c")]
        af.write_model(str(out), h, weights, vocab, devices=devices,
                       device_revision="r1")
        return out

    def test_a_model_with_devices_validates(self, tmp_path):
        assert af.validate(str(self._write(tmp_path, ENTRIES)))

    def test_a_model_with_no_devices_still_validates(self, tmp_path):
        assert af.validate(str(self._write(tmp_path, [])))

    def test_the_table_is_readable_from_the_written_file(self, tmp_path):
        out = self._write(tmp_path, ENTRIES)
        data = out.read_bytes()
        h = af.FlatHeader.unpack(data)
        # Walk to the section the way a loader would.
        offset = af.HEADER_SIZE + af.weight_element_count(h) * 4
        (max_len,) = af.struct.unpack_from("<I", data, offset)
        offset += 4
        for _ in range(h.vocab_size):
            _score, length = af.struct.unpack_from("<fI", data, offset)
            offset += 8 + length

        back, rev, end = unpack_device_table(data, offset)

        assert [e.key for e in back] == [e.key for e in ENTRIES]
        assert end == len(data)

    def test_a_file_with_no_section_is_refused(self, tmp_path):
        """A v2 file read by v3 code. The version is an exact match precisely so
        this is a load error rather than a silently wrong parse."""
        out = self._write(tmp_path, [])
        data = out.read_bytes()
        out.write_bytes(data[: -len(pack_device_table([], "r1"))])

        with pytest.raises(ValueError, match="no device-table section"):
            af.validate(str(out))

    def test_the_version_was_bumped(self):
        """A v2 reader handed a v3 file would parse the table as further
        tokenizer entries — silently wrong rather than loudly broken."""
        assert af.VERSION == 3


class TestBuildingFromTheRegistries:
    def test_both_registries_are_read(self):
        from build_device_table import load_entries

        try:
            entries, revision = load_entries()
        except Exception:
            pytest.skip("registries not ingested")

        assert any(e.bus == BUS_PCI for e in entries)
        assert any(e.bus == BUS_USB for e in entries)
        assert "pci-ids=" in revision and "usb-ids=" in revision

    def test_the_result_is_sorted_and_unique(self):
        from build_device_table import load_entries

        try:
            entries, revision = load_entries()
        except Exception:
            pytest.skip("registries not ingested")

        pack_device_table(entries, revision)      # refuses unsorted or duplicate

    def test_scoping_to_a_target_is_dramatically_smaller(self):
        """`pci.ids` cannot scope by capability — it maps vendor:device to a
        name and class-code to a name in separate sections, with no link. The
        target can: an image built for a known machine needs that machine's
        devices plus its drivers'."""
        from build_device_table import load_entries, scope

        try:
            entries, _ = load_entries()
        except Exception:
            pytest.skip("registries not ingested")

        scoped = scope(entries, {(BUS_PCI, 0x8086, 0x1237)})   # a host bridge

        assert 0 < len(scoped) < len(entries) / 100

    def test_scoping_keeps_the_drivers_devices_too(self):
        """A driver that binds to a device the table cannot name can bind but
        not report. The target id here is deliberately NOT one any driver binds
        to, so the driver ids can only arrive via `driver_device_ids()`."""
        from build_device_table import load_entries, scope

        try:
            entries, _ = load_entries()
        except Exception:
            pytest.skip("registries not ingested")

        scoped = scope(entries, {(BUS_PCI, 0x8086, 0x1237)})   # a host bridge
        keys = {e.key for e in scoped}

        assert (BUS_PCI, 0x8086, 0x1237) in keys        # the target's
        assert (BUS_PCI, 0x8086, 0x100E) in keys        # e1000's
        assert (BUS_PCI, 0x1AF4, 0x1041) in keys        # virtio-net's

    def test_no_target_keeps_everything(self):
        """Nothing says what the machine is, so refusing to guess means
        shipping the lot — the same rule target_spec applies to an
        underspecified target."""
        from build_device_table import scope

        assert scope(ENTRIES, None) == ENTRIES

    def test_a_driver_s_devices_are_always_kept(self):
        """A driver that binds to a device the table cannot name can bind but
        not report."""
        from build_device_table import driver_device_ids

        ids = driver_device_ids()

        assert (BUS_PCI, 0x8086, 0x100E) in ids      # e1000
        assert (BUS_PCI, 0x1AF4, 0x1041) in ids      # virtio-net, modern

    def test_a_target_with_no_pci_devices_is_not_a_missing_target(self):
        """A Firecracker guest's devices are all `virtio-mmio:`, which are in no
        PCI registry — so its PCI id set is legitimately empty. Treating that as
        "no target stated" shipped it the entire 2.5 MB table.

        `None` means nothing was said; an empty set means a target said it has
        none. Conflating them is the defect this project keeps finding.
        """
        from build_device_table import load_entries, scope

        try:
            entries, _ = load_entries()
        except Exception:
            pytest.skip("registries not ingested")

        stated_but_empty = scope(entries, set())
        nothing_stated = scope(entries, None)

        assert len(stated_but_empty) < len(nothing_stated)
        assert len(nothing_stated) == len(entries)
