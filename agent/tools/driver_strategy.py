"""Choose a driver strategy for a device — reuse, port, synthesize, or none.

`strategy` is a field in every driver record and, until now, nothing decided it.
The ordering is not the intuitive one: synthesis looks like the natural fit for
a project that generates its own OS, and it is the most dangerous option
available, because a synthesized DMA programming error is an arbitrary-write
primitive that no prior execution has ever exercised.

So the default is **reuse > port > synthesize**, and the criteria live in
`agent/kernel_spec/drivers/STRATEGY.md` rather than only here — a selector whose
reasoning cannot be argued with is the wrong shape for a decision about ring-0
code.

    python agent/tools/driver_strategy.py --device 8086:100e
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

DRIVERS = ROOT / "agent" / "kernel_spec" / "drivers"
LICENCES = DRIVERS / "licences.yaml"

# Ordered. The first available option wins, which is the whole security
# argument expressed as a list.
ORDER = ("reuse", "port", "synthesize")

# Which document kinds are a normative basis for synthesis. A security advisory
# or a device registry is neither — `pci.ids` tells you a device exists, not how
# to program it.
NORMATIVE_KINDS = ("standard", "architecture-manual", "register-reference",
                   "machine-readable-registers")


class Availability(str, Enum):
    """Three states, because "we had a datasheet" is not availability.

    AVAILABLE   the basis exists, is reachable, and its licence permits this act
    BLOCKED     something exists but cannot be used — say what, and what to do
    ABSENT      there is no basis at all
    """
    AVAILABLE = "available"
    BLOCKED = "blocked"
    ABSENT = "absent"


@dataclass
class Option:
    strategy: str
    availability: Availability
    reason: str
    basis: str = ""            # the document or source that would justify it
    licence: str = ""

    @property
    def usable(self) -> bool:
        return self.availability is Availability.AVAILABLE


@dataclass
class Decision:
    """What was chosen and why, or why nothing was.

    Carries every option considered, not just the winner. A decision that
    records only its conclusion cannot be reviewed — and this is ring-0 code.
    """
    device: str
    identity: str = ""
    chosen: Option | None = None
    options: list[Option] = field(default_factory=list)

    @property
    def refused(self) -> bool:
        return self.chosen is None

    def rationale(self) -> str:
        if self.chosen is None:
            return "no strategy is defensible for this device"
        beaten = [o for o in self.options
                  if ORDER.index(o.strategy) < ORDER.index(self.chosen.strategy)]
        if not beaten:
            return f"{self.chosen.strategy}: {self.chosen.reason}"
        why_not = "; ".join(f"{o.strategy} {o.availability.value} ({o.reason})"
                            for o in beaten)
        return (f"{self.chosen.strategy}: {self.chosen.reason}. "
                f"Preferred options unavailable — {why_not}")


class StrategyError(Exception):
    """Names the device and what could not be established."""


def licence_table() -> dict:
    import yaml
    return yaml.safe_load(LICENCES.read_text(encoding="utf-8"))["licences"]


def _licence_permits(licence: str | None, act: str) -> tuple[bool, str]:
    """Whether a licence permits `reuse` or `port`, and why not when it does not.

    An unrecorded licence is `unknown`, which is unavailable rather than
    assumed-fine.
    """
    table = licence_table()
    key = licence if licence in table else ("unknown" if not licence else None)
    if key is None:
        return False, (f"licence {licence!r} is not in licences.yaml; record its "
                       f"obligations before relying on it")
    entry = table[key]
    verdict = entry[act]
    if verdict == "permitted":
        return True, f"{key} permits {act}"
    if verdict == "depends-on-use":
        return False, (f"{key} obligations depend on how the code is combined "
                       f"and what is distributed — a human must decide, and this "
                       f"table deliberately will not")
    if verdict == "not-applicable":
        return False, f"{key} is a documentation licence, not a code licence"
    return False, (f"{key} makes {act} unavailable"
                   + (f" — {entry['note'].strip().splitlines()[0]}"
                      if entry.get("note") else ""))


def _existing_drivers() -> dict[str, object]:
    """Driver records already in the tree, keyed by every device they bind to.

    A record with `status: implemented` is code that has been run, which is what
    makes reuse the preferred option in the first place.
    """
    from driver_spec import DriverError, load, records
    out: dict[str, object] = {}
    for p in records():
        try:
            rec = load(p)
        except DriverError:
            continue                      # a broken record is driver_spec's problem
        for dev in rec.devices:
            out[dev] = rec
    return out


def _synthesis_basis(vendor_name: str) -> Option:
    """Is there a normative specification, inventoried and ingested?

    Not "does a document exist" — a datasheet nobody can fetch is a citation,
    not a basis. This is the check that separates availability from a citation
    in a record's front-matter.
    """
    from vendor_ingest import CACHE
    from vendor_inventory import load as load_inventory

    try:
        vendors = load_inventory()
    except Exception as exc:
        return Option("synthesize", Availability.BLOCKED,
                      f"inventory unreadable: {exc}")

    match = next((v for v in vendors if v.vendor == vendor_name), None)
    if match is None:
        return Option("synthesize", Availability.ABSENT,
                      f"no vendor {vendor_name!r} in vendors.yaml — nothing "
                      f"records what it publishes")

    specs = [d for d in match.documents if d.kind in NORMATIVE_KINDS]
    if not specs:
        kinds = ", ".join(sorted({d.kind for d in match.documents})) or "none"
        return Option("synthesize", Availability.ABSENT,
                      f"{vendor_name} has no normative specification inventoried "
                      f"(has: {kinds}); a registry or advisory does not say how "
                      f"to program a device")

    for doc in specs:
        cached = (CACHE / match.vendor / doc.id).exists()
        if cached:
            return Option("synthesize", Availability.AVAILABLE,
                          f"{doc.title} is inventoried and ingested",
                          basis=f"{match.vendor}/{doc.id}", licence=doc.licence or "")
    doc = specs[0]
    # Inventoried but not ingested is actionable, and saying which matters.
    return Option("synthesize", Availability.BLOCKED,
                  f"{doc.title} is inventoried but not ingested — run "
                  f"vendor_fetch.py {match.vendor}/{doc.id}",
                  basis=f"{match.vendor}/{doc.id}", licence=doc.licence or "")


# Which inventory vendor publishes the specification for a device.
#
# A table because the two namespaces genuinely do not line up: PCI vendor ids
# are assigned by PCI-SIG, `vendors.yaml` is keyed by *publisher*, and neither
# derives from the other. virtio's ids are registered to Red Hat while its
# specification is published by OASIS; Intel's NIC ids and Intel's SDM happen to
# share a name and that is a coincidence the join should not rely on.
#
# Keyed by device-id prefix first, then by a prefix of the registry's own title.
ID_PREFIX_VENDORS = {
    "virtio-mmio:": "oasis-virtio",
    "1af4:": "oasis-virtio",          # Red Hat's id range, OASIS's specification
}

TITLE_PREFIX_VENDORS = {
    "intel corporation": "intel",
    "advanced micro devices": "amd",
    "nvidia": "nvidia",
    "broadcom": "broadcom-rpi",
}


def _vendor_for(device_id: str) -> str:
    """Which inventory vendor a device id belongs to, or "" when nothing says."""
    from device_registry import Outcome, identify

    for prefix, vendor in ID_PREFIX_VENDORS.items():
        if device_id.startswith(prefix):
            return vendor

    ident = identify(device_id)
    if ident.outcome is not Outcome.IDENTIFIED:
        return ""
    title = ident.title.lower()
    for prefix, vendor in TITLE_PREFIX_VENDORS.items():
        if title.startswith(prefix):
            return vendor
    return ""


def select(device_id: str) -> Decision:
    from device_registry import Outcome, identify

    ident = identify(device_id)
    decision = Decision(device=device_id)
    if device_id.startswith("virtio-mmio:"):
        decision.identity = "virtio device (MMIO transport)"
    elif ident.outcome is Outcome.IDENTIFIED:
        decision.identity = ident.title
    elif ident.outcome is Outcome.UNAVAILABLE:
        raise StrategyError(
            f"{device_id}: no pci.ids registry cached, so the device cannot be "
            f"identified and no strategy can be justified. Run vendor_fetch.py "
            f"— an unidentified device is not the same as an undrivable one")
    else:
        decision.identity = "unidentified"

    existing = _existing_drivers()
    rec = existing.get(device_id.lower())
    if rec is not None and rec.status == "implemented":
        # No external licence lookup here: a record already in this tree
        # recorded its position in `source` when it was written, and
        # driver_spec refuses a port/reuse record that has none.
        decision.options.append(Option(
            "reuse", Availability.AVAILABLE,
            f"{rec.driver} already implements this device in this tree",
            basis=str(rec.path.name if rec.path else rec.driver)))
    else:
        decision.options.append(Option(
            "reuse", Availability.ABSENT,
            "no implemented driver in kernel_spec/drivers/ binds to this device"))

    # Porting needs source, and this tree inventories documents, not source
    # trees. Stating that plainly is better than a check that always says no
    # without saying why.
    decision.options.append(Option(
        "port", Availability.ABSENT,
        "no driver source is inventoried; vendors.yaml records documents, not "
        "source trees, so porting has no catalogued origin to port from"))

    vendor = _vendor_for(device_id)
    if not vendor:
        decision.options.append(Option(
            "synthesize", Availability.ABSENT,
            f"device {device_id} maps to no vendor in vendors.yaml, so no "
            f"specification can be located"))
    else:
        decision.options.append(_synthesis_basis(vendor))

    for name in ORDER:
        option = next(o for o in decision.options if o.strategy == name)
        if option.usable:
            decision.chosen = option
            break
    return decision


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--device", required=True, metavar="ID")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        d = select(args.device)
    except StrategyError as exc:
        print(f"UNDECIDABLE: {exc}", file=sys.stderr)
        return 3

    if args.json:
        import json
        print(json.dumps({
            "device": d.device, "identity": d.identity,
            "chosen": d.chosen.strategy if d.chosen else None,
            "rationale": d.rationale(),
            "options": [{"strategy": o.strategy,
                         "availability": o.availability.value,
                         "reason": o.reason, "basis": o.basis}
                        for o in d.options],
        }, indent=2))
        return 1 if d.refused else 0

    print(f"device:   {d.device}")
    print(f"identity: {d.identity}")
    print()
    for o in d.options:
        mark = "->" if o is d.chosen else "  "
        print(f"{mark} {o.strategy:11s} {o.availability.value:10s} {o.reason}")
        if o.basis:
            print(f"   {'':11s} {'':10s} basis: {o.basis}")
    print()
    if d.refused:
        print("REFUSED: no strategy is defensible for this device. A record "
              "asserting one anyway would validate structurally and be a lie.",
              file=sys.stderr)
        return 1
    print(f"chosen: {d.rationale()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
