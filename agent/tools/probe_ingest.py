"""Turn probe output pasted into chat into a target definition.

D2 derives a target from an AUTON host's provenance; D3 derives one from a
hypervisor's machine type. Bare metal is the class where nothing is decided and
nothing can be derived — the only honest source is the machine itself.

So a user pastes `lspci -nn`, `/proc/cpuinfo` and `dmidecode` output, and this
turns it into a target with `source: probed` on every fact it supports.

**This is the only tool that may write `source: probed`.** D3's derivation is
forbidden from it by test, and that guarantee is worthless from the other
direction if this tool stamps `probed` on anything it inferred.

    lspci -nn | python agent/tools/probe_ingest.py --lspci - --name my-laptop
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

TARGETS = ROOT / "agent" / "kernel_spec" / "targets"
CLASSES = TARGETS / "pci-classes.yaml"

# `01:00.0 Ethernet controller [0200]: Intel Corporation ... [8086:100e] (rev 03)`
# The two bracketed groups are the class and the id. The prose between them is
# the *host's* pci.ids talking, and is deliberately not captured.
LSPCI = re.compile(
    r"^\s*[0-9a-f]{2,4}:[0-9a-f]{2}\.[0-9a-f]\s+"      # bus address
    r".*?\[([0-9a-f]{4})\]"                             # class code
    r".*?\[([0-9a-f]{4}):([0-9a-f]{4})\]",              # vendor:device
    re.IGNORECASE)

CPUINFO = re.compile(r"^(vendor_id|cpu family|model|stepping)\s*:\s*(\S+)\s*$")

# dmidecode fields worth keeping. Everything else in `-t system` and `-t bios`
# is either irrelevant to a build or identifying — see REDACTED below.
DMI_FIELDS = {
    "manufacturer": "manufacturer",
    "product name": "product",
    "vendor": "bios_vendor",
    "version": "bios_version",
}

# Stripped at parse time, never written. `dmidecode` prints the machine's UUID,
# serial number and asset tag, and a target definition is a file that gets
# committed. None of it is needed to build an image. The omission is recorded in
# the output so a reader knows it was deliberate rather than missing.
REDACTED = ("serial number", "uuid", "asset tag", "sku number")

# Manufacturers that unambiguously mean "this is a virtual machine". A string
# not on this list is NOT evidence of bare metal — it may be a hypervisor this
# table has not seen — so an unrecognised value leaves `class` unset.
VM_MANUFACTURERS = {
    "qemu": "vm", "kvm": "vm", "red hat": "vm", "vmware, inc.": "vm",
    "innotek gmbh": "vm", "xen": "vm", "microsoft corporation": "vm",
    "amazon ec2": "vm", "google": "vm", "bochs": "vm", "parallels": "vm",
}


class ProbeError(Exception):
    """Names what could not be parsed, and shows the text."""


@dataclass
class Probe:
    """What the machine said, and what it did not say."""
    devices: list[dict] = field(default_factory=list)
    silicon: dict = field(default_factory=dict)
    firmware: str = ""
    klass: str = ""
    redacted: list[str] = field(default_factory=list)
    unparsed: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _roles() -> tuple[dict, dict, list[str]]:
    import yaml
    data = yaml.safe_load(CLASSES.read_text())
    return data["roles"], data.get("subclasses") or {}, data["drives"]


def parse_lspci(text: str) -> tuple[list[dict], list[str]]:
    """Ids and class codes only.

    `lspci -nn` prints a human name beside each device, but that name comes from
    the *host's* pci.ids, which may be a different revision from the ingested
    one. Capturing it would put an unattributed second source of truth into the
    record; the id is looked up here instead.

    Returns (devices, unparsed). Unparsed lines are returned with their text
    rather than dropped — a device silently missing becomes a driver nobody
    builds.
    """
    roles, subclasses, _ = _roles()
    devices: list[dict] = []
    unparsed: list[str] = []

    for line in text.splitlines():
        if not line.strip():
            continue
        m = LSPCI.match(line)
        if not m:
            unparsed.append(line.rstrip())
            continue
        klass, vendor, device = (g.lower() for g in m.groups())
        devices.append({
            "id": f"{vendor}:{device}",
            "role": subclasses.get(klass) or roles.get(klass[:2], f"class-{klass[:2]}"),
            "source": "probed",
        })
    return devices, unparsed


def parse_cpuinfo(text: str) -> dict:
    """`/proc/cpuinfo` into a silicon block.

    THE TRAP: these values are **already folded**. `errata_table.Signature`
    exists for a raw CPUID `eax`, and folding these a second time would silently
    produce a different machine — a Core i7-8650U (family 6, model 142) would
    become something else, and the errata table would then answer confidently
    about silicon nobody has. Take them as stated.
    """
    found: dict[str, str] = {}
    for line in text.splitlines():
        m = CPUINFO.match(line)
        if m and m.group(1) not in found:
            found[m.group(1)] = m.group(2)
        if len(found) == 4:
            break

    if not found:
        return {}
    return {
        "vendor": found.get("vendor_id", "unknown"),
        "family": found.get("cpu family", "0"),
        "model": found.get("model", "0"),
        "stepping": found.get("stepping", "0"),
        "source": "probed",
    }


def parse_dmidecode(text: str) -> tuple[dict, str, list[str], list[str]]:
    """Firmware and machine class, with identifying fields stripped.

    Returns (fields, klass, redacted, notes). `klass` is empty when the
    manufacturer is not one this table recognises — see the note on
    VM_MANUFACTURERS. Guessing `bare-metal` would make D6's bare-metal rules
    fire wrongly; guessing `vm` would suppress them.
    """
    fields: dict[str, str] = {}
    redacted: list[str] = []
    notes: list[str] = []
    uefi = False

    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key in REDACTED:
            redacted.append(key)
            continue
        if key == "characteristics" or "uefi" in value.lower():
            uefi = uefi or "uefi" in value.lower()
        if key in DMI_FIELDS and value and key not in ("vendor", "version"):
            fields.setdefault(DMI_FIELDS[key], value)
        elif key in DMI_FIELDS:
            fields.setdefault(DMI_FIELDS[key], value)

    klass = ""
    maker = fields.get("manufacturer", "").lower()
    for known, cls in VM_MANUFACTURERS.items():
        if known in maker:
            klass = cls
            break
    if maker and not klass:
        notes.append(
            f"class: manufacturer {fields['manufacturer']!r} is not in the "
            f"recognised-hypervisor table, and an unrecognised name is not "
            f"evidence of bare metal — it may be a hypervisor this table has "
            f"not seen. Left unset deliberately")

    firmware = "uefi" if uefi else ("bios" if fields.get("bios_vendor") else "")
    return fields, klass, sorted(set(redacted)), notes


def probe(lspci: str = "", cpuinfo: str = "", dmidecode: str = "") -> Probe:
    p = Probe()
    if lspci:
        p.devices, p.unparsed = parse_lspci(lspci)
    if cpuinfo:
        p.silicon = parse_cpuinfo(cpuinfo)
    if dmidecode:
        fields, klass, redacted, notes = parse_dmidecode(dmidecode)
        p.klass = klass
        p.redacted = redacted
        p.notes += notes
        uefi = "uefi" if any("uefi" in v.lower() for v in fields.values()) else ""
        p.firmware = uefi or ("bios" if fields.get("bios_vendor") else "")
    return p


def to_target(p: Probe, name: str) -> str:
    """Render a target definition. What was not observed is left out, never
    filled in from somewhere else — D6 then refuses it, naming the gap."""
    lines = ["---", f"target: {name}"]
    if p.klass:
        lines.append(f"class: {p.klass}")
    lines.append("arch: x86_64")
    if p.firmware:
        lines.append(f"firmware: {p.firmware}")
    if p.silicon:
        lines.append("silicon:")
        lines += [f"  {k}: {v}" for k, v in p.silicon.items()]
    lines.append("devices:")
    for d in p.devices:
        lines += [f'  - id: "{d["id"]}"', f"    role: {d['role']}",
                  f"    source: {d['source']}"]
    if p.notes:
        lines.append("assumptions:")
        lines += [f'  - "{n}"' for n in p.notes]
    lines += ["provenance:", "  stated_by: probe-ingest"]
    if p.redacted:
        lines.append(f"  redacted: [{', '.join(p.redacted)}]")
    lines += ["---", "", f"# {name}", "",
              "Read off a running machine and pasted in. Every fact here carries "
              "`source: probed`; anything the probe did not observe is absent "
              "rather than defaulted, and `target_spec.py --validate` will name "
              "what is missing.", ""]
    if p.redacted:
        lines += [
            "## What was stripped", "",
            f"`dmidecode` reports {', '.join(p.redacted)}. None of it is needed "
            f"to build an image and a target definition is a file that gets "
            f"committed, so it was dropped at parse time. The omission is "
            f"recorded here so it reads as deliberate rather than missing.", ""]
    if p.unparsed:
        lines += ["## Lines that did not parse", ""]
        lines += [f"- `{u}`" for u in p.unparsed]
        lines += ["", "Shown rather than dropped: a device silently missing "
                      "becomes a driver nobody builds.", ""]
    return "\n".join(lines)


def _read(arg: str) -> str:
    if not arg:
        return ""
    return sys.stdin.read() if arg == "-" else Path(arg).read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lspci", default="", metavar="FILE", help="'-' for stdin")
    ap.add_argument("--cpuinfo", default="", metavar="FILE")
    ap.add_argument("--dmidecode", default="", metavar="FILE")
    ap.add_argument("--name", required=True, help="the target's name and filename")
    args = ap.parse_args(argv)

    if not any((args.lspci, args.cpuinfo, args.dmidecode)):
        ap.error("give at least one of --lspci, --cpuinfo, --dmidecode")

    p = probe(_read(args.lspci), _read(args.cpuinfo), _read(args.dmidecode))
    print(to_target(p, args.name), end="")

    for u in p.unparsed:
        print(f"UNPARSED: {u}", file=sys.stderr)
    if p.redacted:
        print(f"REDACTED: {', '.join(p.redacted)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
