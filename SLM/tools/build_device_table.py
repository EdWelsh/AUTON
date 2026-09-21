"""Compile the ingested device registries into a model-file section.

The shipped model knows four device ids — `BUS_DEVICES` in build_corpus.py is
QEMU's default PC — and everything else it says about hardware it invents.
Measured at 5 phantom citations per 50 novel turns, against 0 from a lookup.

Meanwhile `.cache/vendor/` holds 21,564 PCI and 20,537 USB ingested records the
running image cannot reach, because they live on the build host.

This puts them inside the model file: one artifact, one version contract, no way
for model and table to drift.

    python SLM/tools/build_device_table.py --out devices.bin
    python SLM/tools/build_device_table.py --manifest doom.json --out doom.bin
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from auton_format import (  # noqa: E402
    BUS_PCI,
    BUS_USB,
    DeviceEntry,
    pack_device_table,
    unpack_device_table,
)

REGISTRIES = ((BUS_PCI, "pci-sig", "pci-ids"), (BUS_USB, "usb-if", "usb-ids"))

# SCOPING BY CAPABILITY IS NOT POSSIBLE FROM THIS DATA, and it is worth saying
# why rather than approximating it.
#
# The PRD's design says the table is "scoped by manifest: a Doom image needs
# input and display entries, not every NIC ever made". That assumes the registry
# knows each device's class. It does not. `pci.ids` lists vendor:device -> name
# in one section and class-code -> name in a separate one, with **no mapping
# between them** — a device's class comes from its PCI configuration space at
# enumeration time, not from the registry.
#
# What can scope the table is the *target*, which is the same rule D7 settled
# for driver selection: a manifest says what the image is for, a target says
# what the machine is. An image built for a known machine needs entries for the
# devices that machine has, plus the devices its drivers bind to. Everything
# else is weight it will never look up.
#
# With no target stated, nothing says what the machine is, so the whole table
# ships. That is the honest default and it is expensive — see the report.


class TableError(Exception):
    """Names what could not be built."""


def load_entries() -> tuple[list[DeviceEntry], str]:
    """Every device in both ingested registries.

    Read through `vendor_ingest`, never by re-parsing the raw files: that parser
    counts what it skips so an extraction rate can be reported honestly, and a
    second one would drift from it.
    """
    from vendor_ingest import ingest

    entries: list[DeviceEntry] = []
    revisions: list[str] = []
    for bus, vendor, doc in REGISTRIES:
        try:
            records, report = ingest(vendor, doc)
        except Exception as exc:
            raise TableError(
                f"{vendor}/{doc} is not ingested ({str(exc).splitlines()[0]}). "
                f"Run vendor_fetch.py — a table built from one registry would "
                f"silently answer 'unknown' for every device on the other bus"
            ) from exc
        revisions.append(f"{doc}={report.get('document_revision', '?')}")
        for r in records:
            vid, _, did = r.key.partition(":")
            try:
                entries.append(DeviceEntry(bus, int(vid, 16), int(did, 16), r.title))
            except ValueError:
                continue                      # not a vvvv:dddd key
    entries.sort(key=lambda e: e.key)
    return entries, "; ".join(revisions)


def driver_device_ids() -> set[tuple[int, int, int]]:
    """Every PCI id a driver record in this tree binds to.

    An image carries drivers, and a driver that binds to a device the table
    cannot name can bind but not report. Read from the records rather than
    hardcoded, so a driver added later is covered without touching this.
    """
    from driver_spec import DriverError, load, records

    out: set[tuple[int, int, int]] = set()
    for path in records():
        try:
            rec = load(path)
        except DriverError:
            continue
        for dev in rec.devices:
            if dev.startswith(("virtio-mmio:", "platform:")):
                continue
            vid, _, did = dev.partition(":")
            try:
                out.add((BUS_PCI, int(vid, 16), int(did, 16)))
            except ValueError:
                continue
    return out


def scope(entries: list[DeviceEntry],
          target_ids: set[tuple[int, int, int]] | None) -> list[DeviceEntry]:
    """Keep what a known machine could present, and drop the rest.

    `None` means no target was stated — nothing says what the machine is, so
    everything ships. Refusing to guess is the rule `target_spec` applies to an
    underspecified target.

    An **empty set** is different and must not be confused with it: a target was
    stated and has no PCI devices at all. A Firecracker guest is exactly that —
    every device it has is `virtio-mmio:`, which is in no PCI registry. Treating
    that as "no target" shipped it the entire 2.5 MB table, which is the
    nothing-said / said-nothing conflation this project keeps finding in its own
    artifacts.
    """
    if target_ids is None:
        return entries

    wanted = set(target_ids) | driver_device_ids()
    return [e for e in entries if e.key in wanted]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", metavar="FILE")
    ap.add_argument("--target", metavar="FILE",
                    help="a target definition whose ids are always kept")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args(argv)

    try:
        entries, revision = load_entries()
    except TableError as exc:
        print(f"CANNOT BUILD: {exc}", file=sys.stderr)
        return 1

    target_ids = None
    if args.target:
        from target_spec import load as load_target
        t = load_target(args.target)
        target_ids = set()
        for d in t.devices:
            if ":" in d.id and not d.id.startswith("virtio-mmio:"):
                v, _, dev = d.id.partition(":")
                try:
                    target_ids.add((BUS_PCI, int(v, 16), int(dev, 16)))
                except ValueError:
                    pass

    scoped = scope(entries, target_ids)
    blob = pack_device_table(scoped, revision)

    pci = sum(1 for e in scoped if e.bus == BUS_PCI)
    usb = sum(1 for e in scoped if e.bus == BUS_USB)
    print(f"{len(scoped):,} entries ({pci:,} PCI, {usb:,} USB), "
          f"{len(blob):,} bytes, revision {revision}")
    if args.stats:
        print(f"  unscoped: {len(entries):,}")
        print(f"  bytes per entry: {len(blob) / max(len(scoped), 1):.1f}")

    if args.out:
        Path(args.out).write_bytes(blob)
        back, rev, end = unpack_device_table(blob, 0)
        if len(back) != len(scoped) or end != len(blob):
            print("round-trip failed", file=sys.stderr)
            return 1
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
