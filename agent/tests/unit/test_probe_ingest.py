"""Turning pasted probe output into a target definition.

D2 derives a target from an AUTON host's provenance; D3 from a hypervisor's
machine type. Bare metal is the class where nothing is decided and nothing can
be derived, so the only honest source is the machine itself.

Two properties carry the weight here, and both are about what the tool must
*not* do: it must not silently drop a device, and it must not write a fact it
did not observe.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from probe_ingest import (  # noqa: E402
    parse_cpuinfo,
    parse_dmidecode,
    parse_lspci,
    probe,
    to_target,
)
from target_spec import TargetError, load  # noqa: E402

TARGETS = ROOT / "agent" / "kernel_spec" / "targets"

LSPCI = """\
00:00.0 Host bridge [0600]: Intel Corporation 440FX - 82441FX PMC [Natoma] [8086:1237] (rev 02)
00:01.0 ISA bridge [0601]: Intel Corporation 82371SB PIIX3 ISA [Natoma/Triton II] [8086:7000]
00:02.0 VGA compatible controller [0300]: Device [1234:1111] (rev 02)
00:03.0 Ethernet controller [0200]: Intel Corporation 82540EM Gigabit Ethernet [8086:100e] (rev 03)
"""

CPUINFO = """\
processor	: 0
vendor_id	: GenuineIntel
cpu family	: 6
model		: 142
model name	: Intel(R) Core(TM) i7-8650U CPU @ 1.90GHz
stepping	: 10
microcode	: 0xf4
"""

DMI = """\
System Information
	Manufacturer: QEMU
	Product Name: Standard PC (i440FX + PIIX, 1996)
	Serial Number: 4C4C4544-0037-3010
	UUID: 03000200-0400-0500-0006-000700080009
	SKU Number: 0A1B2C3D
BIOS Information
	Vendor: SeaBIOS
	Version: 1.16.3
"""


def _written(tmp_path, p, name):
    path = tmp_path / f"{name}.md"
    path.write_text(to_target(p, name))
    return path


class TestLspci:
    def test_devices_are_extracted_with_ids_and_roles(self):
        devices, _ = parse_lspci(LSPCI)

        assert [d["id"] for d in devices] == [
            "8086:1237", "8086:7000", "1234:1111", "8086:100e"]
        assert devices[3]["role"] == "network"

    def test_the_role_comes_from_the_class_not_the_name(self):
        """`lspci -nn` prints a human name beside each device, but it comes from
        the *host's* pci.ids, which may be a different revision from the
        ingested one. Capturing it would put an unattributed second source of
        truth into the record."""
        line = "00:03.0 Ethernet controller [0200]: Totally Made Up Inc Frobnicator [8086:100e]\n"

        devices, _ = parse_lspci(line)

        assert devices[0]["role"] == "network"
        assert "Frobnicator" not in str(devices[0])

    def test_a_line_that_does_not_parse_is_returned_not_dropped(self):
        """A device silently missing becomes a driver nobody builds."""
        devices, unparsed = parse_lspci(LSPCI + "this is not an lspci line\n")

        assert len(devices) == 4
        assert unparsed == ["this is not an lspci line"]

    def test_unparsed_lines_reach_the_target_document(self, tmp_path):
        p = probe(lspci=LSPCI + "garbage line here\n")
        text = to_target(p, "widget")

        assert "garbage line here" in text

    def test_every_device_says_it_was_probed(self):
        devices, _ = parse_lspci(LSPCI)
        assert {d["source"] for d in devices} == {"probed"}

    def test_a_subclass_wins_over_its_base_class(self):
        """Base class 06 covers every kind of bridge. The sub-class entry exists
        because the round-trip against the hand-written qemu-pc.md disagreed —
        added on that evidence, not in anticipation."""
        devices, _ = parse_lspci(LSPCI)

        assert devices[0]["role"] == "host-bridge"    # 0600
        assert devices[1]["role"] == "isa-bridge"     # 0601


class TestCpuinfo:
    def test_the_silicon_block_is_built(self):
        s = parse_cpuinfo(CPUINFO)

        assert s["vendor"] == "GenuineIntel"
        assert s["family"] == "6"
        assert s["model"] == "142"
        assert s["stepping"] == "10"

    def test_values_are_taken_already_folded(self):
        """THE TRAP. `/proc/cpuinfo` reports family and model already folded.
        `Signature.from_cpuid` exists for a raw CPUID eax, and folding these a
        second time silently produces a different machine — after which the
        errata table answers confidently about silicon nobody has.

        Cross-checked against the other route: 0x806EA is the raw signature for
        this part, and folding it must give the same triple cpuinfo states.
        """
        from errata_table import Signature

        folded = Signature.from_cpuid(0x806EA, ())
        s = parse_cpuinfo(CPUINFO)

        assert (int(s["family"]), int(s["model"]), int(s["stepping"])) == (
            folded.family, folded.model, folded.stepping)

    def test_the_first_processor_block_wins(self):
        """A multi-core `/proc/cpuinfo` repeats every field per core. Taking the
        last would be equally valid and equally arbitrary; taking both would
        produce a silicon block with four values in it."""
        s = parse_cpuinfo(CPUINFO + CPUINFO.replace("model\t\t: 142", "model\t\t: 999"))

        assert s["model"] == "142"

    def test_no_cpuinfo_yields_no_silicon(self):
        assert parse_cpuinfo("") == {}


class TestDmidecodeStripsWhatItMustNotKeep:
    def test_a_serial_number_never_appears_in_the_output(self, tmp_path):
        """`dmidecode` prints the machine's serial number, UUID and asset tag.
        None is needed to build an image, and a target definition is a file that
        gets committed."""
        p = probe(lspci=LSPCI, cpuinfo=CPUINFO, dmidecode=DMI)
        text = to_target(p, "widget")

        assert "4C4C4544" not in text
        assert "03000200-0400" not in text
        assert "0A1B2C3D" not in text

    def test_the_stripping_is_recorded_not_silent(self, tmp_path):
        """An omission nobody mentions reads as an omission nobody noticed."""
        p = probe(dmidecode=DMI)

        assert "serial number" in p.redacted
        assert "uuid" in p.redacted
        assert "What was stripped" in to_target(p, "widget")

    def test_firmware_is_read_from_the_bios_block(self):
        p = probe(dmidecode=DMI)
        assert p.firmware == "bios"


class TestTheClassIsNeverGuessed:
    def test_a_recognised_hypervisor_sets_the_class(self):
        p = probe(dmidecode=DMI)
        assert p.klass == "vm"

    def test_an_unrecognised_manufacturer_leaves_the_class_unset(self):
        """Not evidence of bare metal — it may be a hypervisor this table has
        not seen. Guessing `bare-metal` would make D6's bare-metal rules fire
        wrongly; guessing `vm` would suppress them."""
        p = probe(dmidecode=DMI.replace("Manufacturer: QEMU",
                                        "Manufacturer: Acme Robotics Ltd"))

        assert p.klass == ""
        assert any("not evidence of bare metal" in n for n in p.notes)

    def test_an_unset_class_is_refused_by_the_validator(self, tmp_path):
        p = probe(lspci=LSPCI, cpuinfo=CPUINFO,
                  dmidecode=DMI.replace("Manufacturer: QEMU",
                                        "Manufacturer: Acme Robotics Ltd"))

        with pytest.raises(TargetError, match="class"):
            load(_written(tmp_path, p, "acme"))


class TestPartialInputIsPartialNotWrong:
    def test_lspci_alone_yields_devices_and_no_firmware(self, tmp_path):
        """A user pastes what they have. The devices are real and the firmware
        is unknown, and that is a better record than a guessed firmware."""
        p = probe(lspci=LSPCI)
        text = to_target(p, "partial")

        assert "8086:100e" in text
        assert "firmware:" not in text

    def test_a_partial_target_is_refused_naming_what_is_missing(self, tmp_path):
        p = probe(lspci=LSPCI)

        with pytest.raises(TargetError) as exc:
            load(_written(tmp_path, p, "partial"))

        for missing in ("class", "firmware", "silicon"):
            assert missing in str(exc.value)

    def test_adding_the_rest_makes_it_valid(self, tmp_path):
        p = probe(lspci=LSPCI, cpuinfo=CPUINFO, dmidecode=DMI)

        t = load(_written(tmp_path, p, "whole"))

        assert t.klass == "vm"
        assert len(t.devices) == 4


class TestOnlyThisToolSaysProbed:
    def test_every_emitted_fact_says_probed(self, tmp_path):
        """D3 asserts no derivation writes `probed`. That guarantee is worthless
        from the other direction if this tool stamps `probed` on anything it
        inferred."""
        p = probe(lspci=LSPCI, cpuinfo=CPUINFO, dmidecode=DMI)
        t = load(_written(tmp_path, p, "whole"))

        assert {d.source for d in t.devices} == {"probed"}
        assert t.silicon["source"] == "probed"

    def test_nothing_is_filled_in_from_another_source(self, tmp_path):
        """No cpuinfo means no silicon — not a silicon block borrowed from a
        default, and not one zeroed to look complete."""
        p = probe(lspci=LSPCI, dmidecode=DMI)

        assert "silicon:" not in to_target(p, "widget")


class TestRoundTripAgainstTheHandWrittenTarget:
    def test_probing_a_qemu_guest_reproduces_qemu_pc_s_devices(self, tmp_path):
        """`qemu-pc.md` claims `source: probed` but was written by hand. This is
        the tool that makes the claim true rather than asserted."""
        control = load(TARGETS / "qemu-pc.md")
        p = probe(lspci=LSPCI, cpuinfo=CPUINFO, dmidecode=DMI)
        probed = load(_written(tmp_path, p, "probed-qemu"))

        assert ([(d.id, d.role, d.source) for d in probed.devices]
                == [(d.id, d.role, d.source) for d in control.devices])

    def test_the_silicon_differs_and_that_is_the_finding(self, tmp_path):
        """The control records family 6 / model 6 — QEMU's default emulated CPU.
        The cpuinfo here is a real Core i7 passed through. A probe disagreeing
        with a hand-written file is exactly what `source` exists to make
        legible."""
        control = load(TARGETS / "qemu-pc.md")
        p = probe(lspci=LSPCI, cpuinfo=CPUINFO, dmidecode=DMI)

        assert p.silicon["model"] != control.silicon["model"]
        assert p.silicon["source"] == control.silicon["source"] == "probed"
