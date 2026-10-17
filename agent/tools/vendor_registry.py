"""Build the hardware vendor registry: every vendor the open ID databases have ever listed.

vendors.yaml is the curated inventory: the ~40 vendors whose *documents* AUTON
knows how to find. This is the other half, the complete roster, derived rather
than typed. Every vendor that has ever been assigned a PCI or USB vendor id is in
pci.ids or usb.ids (they keep defunct companies), and every CPU vendor a running
machine can report itself as is in the Linux kernel's identity tables:

    pci.ids        PCI vendor id   -> name     (pciutils, GPL-2.0+ / BSD-3)
    usb.ids        USB vendor id   -> name     (usbids,   GPL-2.0+ / BSD-3)
    x86 cpu/*.c    CPUID vendor string         (Linux, GPL-2.0; facts derived)
    cputype.h      Arm MIDR implementer code   (Linux, GPL-2.0; facts derived)

The sources are fetched into .cache/vendor/ by vendor_fetch.py (never committed);
the registry is the derived result, committed with each source's sha256 so a
reader can tell which revision of pci.ids it came from.

A vendor in the registry and not in vendors.yaml has no document coverage. That
is reported, not hidden: "AUTON knows this vendor exists" and "AUTON can read this
vendor's specifications" are different claims.

    python agent/tools/vendor_registry.py --build      # write agent/hardware/registry/vendors.json
    python agent/tools/vendor_registry.py --lookup 8086
    python agent/tools/vendor_registry.py --coverage
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache" / "vendor"
OUT = ROOT / "agent" / "hardware" / "registry" / "vendors.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vendor_inventory import load as load_inventory  # noqa: E402

# (vendor, document id, file name in the cache)
SOURCES = {
    "pci": ("pci-sig", "pci-ids", "pci.ids"),
    "usb": ("usb-if", "usb-ids", "usb.ids"),
    "arm": ("linux-kernel", "linux-arm64-cputype-h", "cputype.h"),
}
X86_VENDOR_FILES = ("intel", "amd", "centaur", "cyrix", "transmeta", "hygon", "zhaoxin",
                    "vortex")

# Corporate suffixes dropped when matching the same company across sources:
# pci.ids says "Intel Corporation", usb.ids "Intel Corp.".
_SUFFIXES = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
             "limited", "llc", "gmbh", "ag", "sa", "srl", "bv", "nv", "plc", "kk", "oy",
             "ab", "as", "spa", "pty", "pte", "the", "group", "holdings", "international",
             "technologies", "technology", "tech", "electronics", "semiconductor",
             "semiconductors", "systems", "microsystems"}


class RegistryError(Exception):
    """Names the missing source and how to fetch it."""


def norm(name: str) -> str:
    """A matching key for one company's name across sources. Lossy on purpose;
    the registry keeps every original spelling beside it."""
    words = re.sub(r"\[.*?\]|\(.*?\)", " ", name.lower())
    words = re.sub(r"[^a-z0-9]+", " ", words).split()
    kept = [w for w in words if w not in _SUFFIXES]
    return " ".join(kept or words)


def cached_file(kind_or_doc: tuple[str, str, str], cache: Path = CACHE) -> tuple[Path, dict]:
    vendor, doc_id, fname = kind_or_doc
    d = cache / vendor / doc_id
    path, prov = d / fname, d / "provenance.json"
    if not path.is_file() or not prov.is_file():
        raise RegistryError(f"{path} not fetched. Run: python agent/tools/vendor_fetch.py "
                            f"--vendor {vendor} --id {doc_id}")
    return path, json.loads(prov.read_text())


def parse_id_db(text: str) -> list[tuple[str, str]]:
    """Top-level `hhhh  Name` vendor lines of pci.ids or usb.ids. usb.ids continues
    with class, HID and language tables, which start at a line beginning `C `
    and use the same indentation, so parsing stops there."""
    out = []
    for line in text.splitlines():
        if line.startswith("C ") or line.startswith("# List of known device classes"):
            break
        m = re.match(r"^([0-9a-fA-F]{4})  (.+?)\s*$", line)
        if m:
            out.append((m.group(1).lower(), m.group(2)))
    return out


def parse_x86_ident(text: str) -> list[str]:
    """CPUID leaf-0 vendor strings from a Linux cpu_dev's `.c_ident = { ... }`."""
    m = re.search(r"\.c_ident\s*=\s*\{([^}]*)\}", text)
    return re.findall(r'"([^"]*)"', m.group(1)) if m else []


def parse_arm_implementers(text: str) -> list[tuple[str, str]]:
    return [(code.lower(), name) for name, code in
            re.findall(r"#define\s+ARM_CPU_IMP_(\w+)\s+(0x[0-9A-Fa-f]+)", text)]


def build(cache: Path = CACHE) -> dict:
    sources, entries = [], {}

    def add(name: str, scheme: str, ident: str):
        key = norm(name)
        e = entries.setdefault(key, {"key": key, "names": [], "ids": []})
        if name not in e["names"]:
            e["names"].append(name)
        e["ids"].append({"scheme": scheme, "id": ident})

    for scheme in ("pci", "usb"):
        path, prov = cached_file(SOURCES[scheme], cache)
        sources.append({"scheme": scheme, "document": prov["document_id"],
                        "sha256": prov["sha256"], "source": prov["source"],
                        "licence": prov.get("licence")})
        for ident, name in parse_id_db(path.read_text(encoding="utf-8", errors="replace")):
            add(name, scheme, ident)

    path, prov = cached_file(SOURCES["arm"], cache)
    sources.append({"scheme": "arm-midr-implementer", "document": prov["document_id"],
                    "sha256": prov["sha256"], "source": prov["source"],
                    "licence": prov.get("licence")})
    arm_names = {"ARM": "Arm Limited", "APM": "Applied Micro Circuits", "CAVIUM": "Cavium",
                 "BRCM": "Broadcom", "QCOM": "Qualcomm", "NVIDIA": "NVIDIA",
                 "FUJITSU": "Fujitsu", "HISI": "HiSilicon", "APPLE": "Apple",
                 "AMPERE": "Ampere Computing", "MICROSOFT": "Microsoft"}
    for code, sym in parse_arm_implementers(path.read_text()):
        add(arm_names.get(sym, sym.title()), "arm-midr-implementer", code)

    for v in X86_VENDOR_FILES:
        path, prov = cached_file(("linux-kernel", f"linux-x86-cpu-{v}-c", f"{v}.c"), cache)
        sources.append({"scheme": "x86-cpuid-vendor", "document": prov["document_id"],
                        "sha256": prov["sha256"], "source": prov["source"],
                        "licence": prov.get("licence")})
        for ident in parse_x86_ident(path.read_text()):
            add(X86_VENDOR_NAMES.get(ident, ident.strip()), "x86-cpuid-vendor", ident)

    covered = {norm(v.vendor.replace("-", " ")): v.vendor for v in load_inventory()}
    covered.update(INVENTORY_ALIASES)
    vendors = sorted(entries.values(), key=lambda e: e["key"])
    for e in vendors:
        e["inventory"] = covered.get(e["key"])
    return {"generated_from": sources, "count": len(vendors), "vendors": vendors}


# The company behind each CPUID vendor string (Linux names the file, not the firm).
X86_VENDOR_NAMES = {
    "GenuineIntel": "Intel Corporation", "AuthenticAMD": "Advanced Micro Devices",
    "CentaurHauls": "Centaur Technology", "CyrixInstead": "Cyrix",
    "Geode by NSC": "National Semiconductor", "GenuineTMx86": "Transmeta",
    "TransmetaCPU": "Transmeta", "HygonGenuine": "Hygon",
    "  Shanghai  ": "Zhaoxin", "Vortex86 SoC": "DM&P Electronics",
}

# Registry keys that mean an inventory vendor whose short name does not normalise
# to the same key ("amd" vs "advanced micro devices").
INVENTORY_ALIASES = {
    "intel": "intel", "advanced micro devices": "amd", "amd": "amd", "arm": "arm",
    "nvidia": "nvidia", "texas instruments": "ti", "nxp": "nxp",
    "stmicroelectronics": "st", "microchip": "microchip", "broadcom": "broadcom-rpi",
    "rockchip": "rockchip", "rockchip electronics": "rockchip", "allwinner": "allwinner",
    "qualcomm": "qualcomm", "apple": "apple", "sifive": "sifive", "loongson": "loongson",
    "ibm": "ibm-openpower", "international business machines": "ibm-openpower",
    "microsoft": "microsoft",
}


def dumps(reg: dict) -> str:
    """One vendor per line, so a refreshed pci.ids shows up as a readable diff."""
    head = json.dumps({k: v for k, v in reg.items() if k != "vendors"}, ensure_ascii=False)
    rows = ",\n".join(json.dumps(e, ensure_ascii=False) for e in reg["vendors"])
    return head[:-1] + ', "vendors": [\n' + rows + "\n]}\n"


def lookup(registry: dict, query: str) -> list[dict]:
    q, qn = query.lower(), norm(query)
    return [e for e in registry["vendors"]
            if e["key"] == qn or any(i["id"].lower() == q for i in e["ids"])]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--lookup")
    ap.add_argument("--coverage", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.build:
            reg = build()
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(dumps(reg))
            print(f"{OUT.relative_to(ROOT)}: {reg['count']} vendors from "
                  f"{len(reg['generated_from'])} sources")
            return 0
        reg = json.loads(OUT.read_text())
    except RegistryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.lookup:
        hits = lookup(reg, args.lookup)
        for e in hits:
            ids = ", ".join(f"{i['scheme']}:{i['id']}" for i in e["ids"])
            print(f"{' / '.join(e['names'])}  [{ids}]  documents: {e['inventory'] or 'none'}")
        return 0 if hits else 1
    if args.coverage:
        withdocs = sum(1 for e in reg["vendors"] if e["inventory"])
        by = {}
        for e in reg["vendors"]:
            for i in e["ids"]:
                by[i["scheme"]] = by.get(i["scheme"], 0) + 1
        print(f"{reg['count']} vendors; {withdocs} with document coverage in vendors.yaml")
        for k, n in sorted(by.items()):
            print(f"  {k:24} {n}")
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
