"""The framebuffer and PS/2 records, and the table behind the scancodes.

The C arithmetic is proved by `tests/kernel/run_display_test.sh` under ASan and
UBSan. What is checked here is what Python can see: that the record files say
what they claim, and that the host reference and the data table agree.

A reference that has drifted from its table is worse than either alone — the
table is reviewable and the reference is executable, and a driver generated from
one while tested against the other passes its tests and does the wrong thing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from driver_spec import load, records, validate  # noqa: E402
from target_spec import Identification, identify  # noqa: E402

DRIVERS = ROOT / "agent" / "kernel_spec" / "drivers"
SCANCODES = DRIVERS / "scancodes.yaml"
REFERENCE = ROOT / "tests" / "kernel" / "display_reference" / "display_ref.c"


def _table():
    return yaml.safe_load(SCANCODES.read_text())


def _reference_map(array_name):
    """Parse the designated initialisers out of the reference's C array."""
    text = REFERENCE.read_text()
    body = text.split(f"{array_name}[128] = {{", 1)[1].split("};", 1)[0]
    escapes = {r"\\": "\\", r"\'": "'"}
    out = {}
    for code, ch in re.findall(r"\[(0x[0-9a-f]{2})\]='(\\?.)'", body):
        out[int(code, 16)] = escapes.get(ch, ch)
    return out


class TestTheReferenceAgreesWithTheTable:
    def test_every_printable_scancode_matches_unshifted(self):
        """The table is the source of truth; the reference is what runs."""
        table = _table()["printable"]
        ref = _reference_map("unshifted")

        for code, (plain, _shift) in table.items():
            assert ref.get(code) == plain, f"0x{code:02x}"

    def test_every_printable_scancode_matches_shifted(self):
        table = _table()["printable"]
        ref = _reference_map("shifted_map")

        for code, (_plain, shift) in table.items():
            assert ref.get(code) == shift, f"0x{code:02x}"

    def test_the_reference_maps_nothing_the_table_does_not(self):
        """Drift in the other direction: a key the reference knows and the
        table does not is a key nobody reviewed."""
        table = set(_table()["printable"])

        for name in ("unshifted", "shifted_map"):
            assert set(_reference_map(name)) <= table, name

    def test_control_keys_produce_no_character(self):
        """Enter is a key, not a character. A table that gave it one would put a
        stray byte into every line."""
        control = set(_table()["control"])
        printable = set(_table()["printable"])

        assert control & printable == set()

    def test_the_table_names_its_scancode_set(self):
        """Sets 2 and 3 exist and the controller translates by default. A driver
        assuming translation is off reads different bytes entirely."""
        assert _table()["set"] == 1


class TestTheRecords:
    def test_all_driver_records_validate(self):
        for p in records():
            validate(p)

    def test_the_framebuffer_binds_to_no_display_device(self):
        """It works with whatever hardware the loader configured, so binding it
        to a display id would claim something untrue."""
        rec = load(DRIVERS / "framebuffer.md")

        assert rec.devices == ["platform:multiboot2-framebuffer"]

    def test_its_basis_is_inventoried(self):
        """The defect V4 caught in virtio-net.md was a citation nobody could
        produce. This one resolves."""
        state, detail = identify("platform:multiboot2-framebuffer")

        assert state is Identification.IDENTIFIED
        assert "multiboot2-spec" in detail

    def test_the_keyboard_is_accepted_by_a_recorded_decision(self):
        """w11 intent-G: a person accepted it on convention plus tests. The
        record says so and keeps the history of why it was undrivable."""
        rec = load(DRIVERS / "ps2-keyboard.md")

        assert rec.status == "specified"
        assert "accepted" in rec.body.lower()
        assert "undrivable" in rec.body.lower()

    def test_acceptance_is_not_an_identification(self):
        """Nothing claims a document exists: the selector's refusal stands and
        `identify` still answers UNKNOWN. The decision is recorded beside it."""
        from target_spec import platform_acceptance

        state, _ = identify("platform:i8042")
        assert state is Identification.UNKNOWN
        accepted = platform_acceptance("platform:i8042")
        assert accepted and accepted["evidence"]

    def test_acceptance_admits_specified_and_reports_it(self):
        report = validate(DRIVERS / "ps2-keyboard.md")

        assert report.accepted == ["platform:i8042"]

    def test_acceptance_never_admits_implemented(self, tmp_path):
        """`implemented` still needs a mapping and an observed pass; a decision
        to proceed without a specification is not evidence the driver works."""
        from driver_spec import DriverError

        text = (DRIVERS / "ps2-keyboard.md").read_text().replace(
            "status: specified", "status: implemented")
        (tmp_path / "ps2-keyboard.md").write_text(text)
        with pytest.raises(DriverError):
            validate(tmp_path / "ps2-keyboard.md")

    def test_an_unaccepted_platform_device_is_still_refused(self, tmp_path):
        from driver_spec import DriverError

        text = (DRIVERS / "ps2-keyboard.md").read_text().replace(
            "platform:i8042", "platform:nosuch-device")
        (tmp_path / "ps2-keyboard.md").write_text(text)
        with pytest.raises(DriverError):
            validate(tmp_path / "ps2-keyboard.md")

    def test_it_does_not_cite_a_document_nobody_can_produce(self):
        """Writing `specification: "Intel 8042 datasheet"` would repeat exactly
        the defect V4 found, knowingly."""
        rec = load(DRIVERS / "ps2-keyboard.md")

        assert "none" in rec.specification.lower()

    def test_an_undrivable_record_may_still_name_an_unidentifiable_device(self, tmp_path):
        """No record in the tree is undrivable any more, but the status must
        still admit an unidentifiable device — it is the one thing it is for."""
        text = (DRIVERS / "ps2-keyboard.md").read_text().replace(
            "platform:i8042", "platform:nosuch-device").replace(
            "status: specified", "status: undrivable")
        (tmp_path / "ps2-keyboard.md").write_text(text)
        validate(tmp_path / "ps2-keyboard.md")      # does not raise

    def test_the_keyboard_record_names_the_machines_it_would_serve(self):
        """Firecracker's i8042 is vestigial — reset signalling with no keyboard
        behind it — so binding there waits forever for a keypress."""
        body = load(DRIVERS / "ps2-keyboard.md").body

        assert "vestigial" in body
        assert "microVM" in body or "microvm" in body


class TestWhatDoomStillNeeds:
    """The PRD calls Doom the headline intent. "Framebuffer and input now
    exist" is a claim to check, not to assume."""

    def test_both_capabilities_are_now_specified(self):
        from capability_slice import load_specs

        provided = {c for s in load_specs().values() for c in s.provides}

        assert {"framebuffer", "input"} <= provided

    def test_neither_is_implemented(self):
        """Specified is not implemented, and the source map now says so
        honestly rather than pointing at a directory that never existed."""
        from build_manifest import SourceMap

        assert "framebuffer" not in SourceMap.load().capabilities

    def test_doom_has_a_service_spec_and_it_is_not_a_stub(self):
        """w11 intent-G emitted it through intent-C's handoff and wrote the
        body; the gate refuses a spec still carrying the stub marker."""
        from intent_service import STUB_MARKER

        spec = ROOT / "agent" / "kernel_spec" / "services" / "play-doom.md"
        assert spec.exists()
        assert STUB_MARKER not in spec.read_text()

    def test_module_asset_is_still_unmapped(self):
        """The third blocker, and not a driver problem — Doom needs its WAD
        handed in as a boot module."""
        from build_manifest import SourceMap

        assert "module-asset" not in SourceMap.load().capabilities
