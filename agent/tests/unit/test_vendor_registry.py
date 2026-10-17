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


def test_each_id_keeps_the_name_its_source_gives(tmp_path):
    reg = vr.build(_cache(tmp_path))
    ibm = vr.lookup(reg, "04b3")[0]
    assert {i["id"]: i["name"] for i in ibm["ids"]} == {"1014": "IBM", "04b3": "IBM Corp."}


def test_a_shared_generic_word_does_not_make_one_company(tmp_path):
    """'Graphics Microsystems' (13d4) and 'Graphics Technology (HK)' (256c) are two
    firms; so are 'Crystal Group' and 'Crystal Semiconductor'."""
    cache = _cache(tmp_path)
    (cache / "pci-sig" / "pci-ids" / "pci.ids").write_text(
        PCI + "13d4  Graphics Microsystems Inc\n256c  Graphics Technology (HK) Co., Ltd.\n"
        "13a0  Crystal Group Inc\n")
    (cache / "usb-if" / "usb-ids" / "usb.ids").write_text(
        "046f  Crystal Semiconductor\n08de  ???\n18f8  [Maxxter]\n0b0b  ???\n" + USB)
    reg = vr.build(cache)
    assert vr.lookup(reg, "256c")[0]["names"] == ["Graphics Technology (HK) Co., Ltd."]
    assert vr.lookup(reg, "046f")[0]["names"] == ["Crystal Semiconductor"]
    # names with nothing to match on are never filed together under ""
    assert all(e["key"] for e in reg["vendors"])
    assert [i["id"] for i in vr.lookup(reg, "08de")[0]["ids"]] == ["08de"]
    assert vr.lookup(reg, "18f8")[0]["key"] == "maxxter"


def test_every_c_ident_in_a_file_is_read(tmp_path):
    """cyrix.c holds two cpu_devs: CyrixInstead and the NSC Geode's own string."""
    cache = _cache(tmp_path)
    (cache / "linux-kernel" / "linux-x86-cpu-cyrix-c" / "cyrix.c").write_text(
        'static const struct cpu_dev cyrix_cpu_dev = { .c_ident = { "CyrixInstead" }, };\n'
        'static const struct cpu_dev nsc_cpu_dev = { .c_ident = { "Geode by NSC" }, };\n')
    reg = vr.build(cache)
    assert vr.lookup(reg, "Geode by NSC")[0]["names"] == ["National Semiconductor"]


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
    assert all(e["key"] and all(i["name"] for i in e["ids"]) for e in reg["vendors"])
    assert vr.lookup(reg, "Geode by NSC")
