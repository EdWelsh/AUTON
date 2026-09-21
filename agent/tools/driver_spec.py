"""Parse and validate a driver decision record.

A target says a device is present; the capability index says whether the tree
can drive it. Neither says how a driver came to exist or how anyone would know
it works, and a driver that cannot say how its claim was checked is an
assertion — the most expensive kind to be wrong about when it is about hardware.

Mirrors `target_spec.py` deliberately: same refusal style, same three-valued
identification, same rule that unverifiable is not valid.

    python agent/tools/driver_spec.py --validate agent/kernel_spec/drivers/e1000.md
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from target_spec import (  # noqa: E402
    EXIT_REFUSED,
    EXIT_UNVERIFIABLE,
    MMIO_ID,
    PCI_ID,
    PLATFORM_ID,
    Identification,
    _front_matter,
    identify,
    platform_acceptance,
)

DRIVERS = ROOT / "agent" / "kernel_spec" / "drivers"

REQUIRED = ("driver", "devices", "provides", "strategy", "verification", "status")
STRATEGIES = ("reuse", "port", "synthesize")
STATUSES = ("implemented", "specified", "undrivable")

# What each strategy must additionally say. `synthesize` without a citation
# means "written from memory", which is the phantom-device defect with a
# register map attached; `port`/`reuse` without a source is a legal question
# that surfaces at distribution.
STRATEGY_REQUIRES = {
    "synthesize": "specification",
    "port": "source",
    "reuse": "source",
}

# A verification entry must be one of these. Prose describing how one *might*
# check is not a check.
VERIFICATION_PREFIXES = ("cmd:", "marker:")


class DriverError(Exception):
    """Names the field."""


@dataclass
class DriverRecord:
    driver: str
    devices: list[str]
    provides: list[str]
    strategy: str
    verification: list[str]
    status: str
    source: str = ""
    specification: str = ""
    path: Path | None = None
    body: str = ""

    @property
    def basis(self) -> str:
        """What this driver rests on — a document or an existing implementation."""
        return self.specification or self.source


def _expects_list(key: str) -> bool:
    return key in ("devices", "provides", "verification")


def _as_list(value) -> list[str]:
    """Accept both list forms.

    `service_spec` writes `requires: [udp, allocator]` inline; targets use
    indented blocks. A driver record should look like a service spec — it sits
    beside one in kernel_spec/ — so both are admitted here rather than forcing
    one. Normalised locally instead of in the shared front-matter parser, which
    targets also use and which has no reason to change.
    """
    if isinstance(value, list):
        return [str(v).strip().strip('"').strip("'") for v in value]
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [v.strip().strip('"').strip("'") for v in inner.split(",")]
    return [text] if text else []


def records(directory: Path = None) -> list[Path]:
    """Every driver record in a directory.

    Distinguished by having front-matter, not by filename. `README.md` and
    `STRATEGY.md` are prose that lives beside the records, and a list of names
    to skip grows silently wrong the first time someone adds a third.
    """
    directory = directory or DRIVERS
    return [p for p in sorted(directory.glob("*.md"))
            if p.read_text(encoding="utf-8").startswith("---\n")]


def load(path: str | Path) -> DriverRecord:
    path = Path(path)
    if not path.exists():
        raise DriverError(f"{path}: no such driver record")
    text = path.read_text(encoding="utf-8")

    # target_spec's parser decides list-ness by key name, and these keys differ.
    import target_spec
    from target_spec import TargetError
    prev, target_spec._expects_list = target_spec._expects_list, _expects_list
    try:
        data = _front_matter(text, path)
    except TargetError as exc:
        # The parser is shared with targets; the error should not be. A caller
        # catching DriverError must not be surprised by a TargetError from a
        # driver record.
        raise DriverError(str(exc)) from exc
    finally:
        target_spec._expects_list = prev

    missing = [f for f in REQUIRED if f not in data]
    if missing:
        raise DriverError(f"{path.name}: missing field(s): {', '.join(missing)}")
    if data["driver"] != path.stem:
        raise DriverError(
            f"{path.name}: 'driver' is {data['driver']!r} but the file is "
            f"{path.stem!r}; they address the same thing")
    if data["strategy"] not in STRATEGIES:
        raise DriverError(
            f"{path.name}: strategy {data['strategy']!r} not one of "
            f"{', '.join(STRATEGIES)}")
    if data["status"] not in STATUSES:
        raise DriverError(
            f"{path.name}: status {data['status']!r} not one of "
            f"{', '.join(STATUSES)}")

    needed = STRATEGY_REQUIRES[data["strategy"]]
    if not data.get(needed):
        why = ("a citation, or it means written from memory"
               if needed == "specification"
               else "what it came from and its licence")
        raise DriverError(
            f"{path.name}: strategy {data['strategy']!r} requires {needed!r} — "
            f"{why}")

    devices = [d.lower() for d in _as_list(data.get("devices", []))]
    if not devices:
        raise DriverError(
            f"{path.name}: 'devices' is empty. A driver that binds to no device "
            f"is a library")
    for d in devices:
        if not (PCI_ID.match(d) or MMIO_ID.match(d) or PLATFORM_ID.match(d)):
            raise DriverError(
                f"{path.name}: device id {d!r} is none of vvvv:dddd (PCI), "
                f"virtio-mmio:<type> (MMIO) or platform:<name> (no enumerable "
                f"bus)")

    verification = _as_list(data.get("verification", []))
    if not verification:
        raise DriverError(
            f"{path.name}: 'verification' is empty. An image that claims a "
            f"driver works is making the claim a user acts on")
    for v in verification:
        if not v.startswith(VERIFICATION_PREFIXES):
            raise DriverError(
                f"{path.name}: verification entry {v!r} is prose. Each entry "
                f"must start with 'cmd:' or 'marker:' — a description of how "
                f"one might check is not a check")

    return DriverRecord(
        driver=data["driver"], devices=devices,
        provides=_as_list(data.get("provides", [])), strategy=data["strategy"],
        verification=verification, status=data["status"],
        source=data.get("source", ""), specification=data.get("specification", ""),
        path=path, body=text.split("\n---\n", 1)[-1],
    )


@dataclass
class Report:
    record: DriverRecord
    unverifiable: list[str] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)
    accepted: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unverifiable


def check_devices(rec: DriverRecord) -> Report:
    """Every device id must resolve against the registry for its transport.

    Unlike a target, a record cannot appeal to `source: probed` — there is no
    machine here to have observed anything. An id in no registry is refused.
    """
    report = Report(record=rec)
    phantom = []
    for d in rec.devices:
        state, detail = identify(d)
        if state is Identification.IDENTIFIED:
            continue
        if state is Identification.UNAVAILABLE:
            report.unverifiable.append(d)
        else:
            phantom.append(f"{d} — {detail}")
    if phantom and rec.status == "specified" and all(
            platform_acceptance(p.split(" — ")[0]) for p in phantom):
        # A person accepted the device without a specification, and recorded
        # the evidence in platform-devices.yaml. That admits `specified` —
        # never `implemented`, which check_status still gates on a mapping.
        report.accepted = [p.split(" — ")[0] for p in phantom]
        return report
    if phantom and rec.status == "undrivable":
        # `undrivable` means exactly this: the device is real and nothing
        # specifies it. Refusing the record would leave no way to say so, and
        # README.md admits the status for that reason.
        return report
    if phantom:
        raise DriverError(
            f"{rec.path.name}: device id(s) in no registry: {'; '.join(phantom)}. "
            f"A record cannot claim `probed` — there is no machine here to have "
            f"observed anything. Name a real device")
    return report


def check_status(rec: DriverRecord, report: Report, tree: Path | None = None) -> None:
    """`status: implemented` is a claim about this tree.

    Refused when `provides` has no mapping in source_map.yaml, because that
    combination says the driver is in an image that does not contain it — the
    same false claim `[gate: capabilities]` refuses one level down.
    `status: specified` with no mapping is the normal state before V5 runs, and
    is reported rather than refused: a record for a driver that does not exist
    yet is the point of having records.
    """
    from build_manifest import SourceMap

    source_map = SourceMap.load()
    mapped = set(source_map.capabilities) | set(source_map.core_provides)
    report.unmapped = sorted(c for c in rec.provides if c not in mapped)

    # A mapping to a directory that has never existed is the same false claim
    # wearing a disguise. Checking it needs a tree, which a record does not
    # have — so the stricter check runs only where one is known, and a record
    # still validates standalone.
    if tree is not None:
        from build_manifest import ManifestError, resolve
        try:
            _, _, r = resolve(list(rec.provides), [], tree)
        except ManifestError:
            r = {}
        phantom = set(r.get("phantom_capabilities") or []) & set(rec.provides)
        if phantom:
            report.unmapped = sorted(set(report.unmapped) | phantom)

    if rec.status == "implemented" and report.unmapped:
        raise DriverError(
            f"{rec.path.name}: status 'implemented' but "
            f"{', '.join(report.unmapped)} has no mapping in source_map.yaml. "
            f"That combination claims the driver is in an image that does not "
            f"contain it. Use 'specified' until it is written")


def validate(path: str | Path, tree: Path | None = None) -> Report:
    rec = load(path)
    report = check_devices(rec)
    check_status(rec, report, tree)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--validate", metavar="FILE")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--tree", metavar="DIR",
                    help="also check that each provided capability's source "
                         "mapping matches something in this tree")
    args = ap.parse_args(argv)

    paths = (records() if args.all
             else [Path(args.validate)] if args.validate else [])
    if not paths:
        ap.error("give --validate FILE or --all")

    rc = 0
    for p in paths:
        try:
            r = validate(p, Path(args.tree) if args.tree else None)
        except DriverError as exc:
            print(f"INVALID: {exc}", file=sys.stderr)
            rc = max(rc, EXIT_REFUSED)
            continue
        rec = r.record
        status = "OK" if r.ok else "UNVERIFIED"
        print(f"{status} {p.name}: {rec.strategy}/{rec.status}, "
              f"{len(rec.devices)} device(s), {len(rec.verification)} check(s)")
        if r.accepted:
            print(f"   accepted without a specification: {', '.join(r.accepted)} "
                  f"— a recorded decision in platform-devices.yaml, not a citation")
        if r.unmapped:
            print(f"   not implemented in this tree: {', '.join(r.unmapped)} "
                  f"(status '{rec.status}' — expected before the driver is written)")
        if r.unverifiable:
            print(f"   unverifiable: {', '.join(r.unverifiable)} — no registry "
                  f"cached", file=sys.stderr)
            rc = max(rc, EXIT_UNVERIFIABLE)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
