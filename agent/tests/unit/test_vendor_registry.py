"""The vendor registry is derived from the ID databases, never typed."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

import vendor_registry as vr  # noqa: E402

PCI = """# pci.ids
8086  Intel Corporation
\t100e  82540EM Gigabit Ethernet Controller
1014  IBM
"""
USB = """8086  Intel Corp.
04b3  IBM Corp.
C 00  (Defined at Interface level)
\t01  Audio
"""
ARM = "#define ARM_CPU_IMP_ARM\t\t\t0x41\n#define ARM_CPU_IMP_APPLE\t\t0x61\n"


def _cache(tmp_path: Path) -> Path:
    def put(vendor, doc, name, text):
        d = tmp_path / vendor / doc
        d.mkdir(parents=True)
        (d / name).write_text(text)
        (d / "provenance.json").write_text(json.dumps(
            {"document_id": doc, "sha256": "0" * 64, "source": "test", "licence": "x"}))
    put("pci-sig", "pci-ids", "pci.ids", PCI)
    put("usb-if", "usb-ids", "usb.ids", USB)
    put("linux-kernel", "linux-arm64-cputype-h", "cputype.h", ARM)
    for v in vr.X86_VENDOR_FILES:
        ident = {"intel": "GenuineIntel", "amd": "AuthenticAMD"}.get(v, v)
        put("linux-kernel", f"linux-x86-cpu-{v}-c", f"{v}.c",
            f'static const struct cpu_dev x = {{ .c_ident = {{ "{ident}" }}, }};')
    return tmp_path


def test_one_company_across_sources_is_one_entry(tmp_path):
    reg = vr.build(_cache(tmp_path))
    intel = vr.lookup(reg, "8086")
    assert len(intel) == 1
    schemes = {i["scheme"] for i in intel[0]["ids"]}
    assert schemes == {"pci", "usb", "x86-cpuid-vendor"}
    assert intel[0]["inventory"] == "intel"


def test_usb_class_tables_are_not_vendors(tmp_path):
    reg = vr.build(_cache(tmp_path))
    assert not vr.lookup(reg, "00")
    assert not any("Audio" in n for e in reg["vendors"] for n in e["names"])


def test_a_vendor_with_no_documents_says_so(tmp_path):
    reg = vr.build(_cache(tmp_path))
    apple = vr.lookup(reg, "0x61")[0]
    assert apple["inventory"] == "apple"     # inventory records Apple as a gap
    assert all(e["inventory"] is None or isinstance(e["inventory"], str)
               for e in reg["vendors"])


def test_every_source_is_recorded_with_its_hash(tmp_path):
    reg = vr.build(_cache(tmp_path))
    assert len(reg["generated_from"]) == 3 + len(vr.X86_VENDOR_FILES)
    assert all(len(s["sha256"]) == 64 for s in reg["generated_from"])


def test_a_missing_source_names_the_fetch_command(tmp_path):
    with pytest.raises(vr.RegistryError, match="vendor_fetch.py --vendor pci-sig"):
        vr.build(tmp_path)


def test_the_committed_registry_round_trips():
    reg = json.loads(vr.OUT.read_text())
    assert reg["count"] == len(reg["vendors"]) > 4000
    assert json.loads(vr.dumps(reg)) == reg
