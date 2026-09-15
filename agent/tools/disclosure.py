"""Private records for silicon findings, and the embargo clock.

The PRD is explicit: *"A finding with no disclosure path is not a deliverable."*
This exists before the conformance harness does, so the first real finding does
not have to invent a process in a hurry.

Records live in `.disclosure/`, which is gitignored. The tool **refuses a
tracked path** — publishing a finding by accident is the failure this whole
policy exists to prevent, and a git commit is publication.

    python agent/tools/disclosure.py record --silicon 6:151:2 --vendor intel \
        --spec "SDM vol 2, CMPXCHG8B" --expected "#UD" --observed "hang"
    python agent/tools/disclosure.py list
    python agent/tools/disclosure.py due
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / ".disclosure"
CONTACTS = ROOT / "agent" / "hardware" / "disclosure" / "contacts.yaml"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from vendor_inventory import is_tracked_path  # noqa: E402

STATUSES = ("private", "reported", "acknowledged", "disputed", "published", "withdrawn")
CLASSES = ("fault", "semantic")
REQUIRED = ("silicon", "vendor", "spec_citation", "expected", "observed", "reproducer", "class")


class DisclosureError(Exception):
    pass


@dataclass
class Finding:
    id: str
    silicon: str                 # family:model:stepping[:microcode]
    vendor: str
    spec_citation: str
    expected: str
    observed: str
    reproducer: str
    klass: str
    status: str = "private"
    found_at: str = ""
    reported_at: str = ""
    embargo_until: str = ""
    dispute: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["class"] = d.pop("klass")
        return d


def _contacts() -> dict:
    data = yaml.safe_load(CONTACTS.read_text(encoding="utf-8"))
    return {v["vendor"]: v for v in data["vendors"]}


def _store(path: Path | None = None) -> Path:
    store = path or STORE
    if is_tracked_path(str(store)):
        raise DisclosureError(
            f"refusing to write findings into {store}: it is tracked. "
            f"A finding is private until disclosure, and a commit is "
            f"publication. Use an untracked path such as .disclosure/."
        )
    store.mkdir(parents=True, exist_ok=True)
    return store


def record(silicon: str, vendor: str, spec_citation: str, expected: str,
           observed: str, reproducer: str, klass: str = "semantic",
           store: Path | None = None, notes: str = "") -> Finding:
    contacts = _contacts()
    if vendor not in contacts:
        raise DisclosureError(
            f"no published security contact for {vendor!r}. Known: "
            f"{', '.join(sorted(contacts))}. A finding cannot be filed against "
            f"a vendor nobody knows how to reach — add them to contacts.yaml first."
        )
    if klass not in CLASSES:
        raise DisclosureError(f"class must be one of {', '.join(CLASSES)}")
    for name, value in (("spec_citation", spec_citation), ("expected", expected),
                        ("observed", observed), ("reproducer", reproducer)):
        if not str(value).strip():
            raise DisclosureError(
                f"{name} is required. A divergence is divergence *from something*; "
                f"without it there is only a surprise, and a finding without "
                f"provenance is a rumour."
            )
    parts = silicon.split(":")
    if len(parts) < 3:
        raise DisclosureError(
            f"silicon {silicon!r} must be family:model:stepping[:microcode]. "
            f"'Some Intel chips' is not a finding."
        )

    now = datetime.now(timezone.utc)
    days = contacts[vendor].get("embargo_default_days", 90)
    digest = hashlib.sha256(
        f"{silicon}|{spec_citation}|{expected}|{observed}".encode()).hexdigest()[:12]
    finding = Finding(
        id=f"AUTON-{now:%Y%m%d}-{digest}", silicon=silicon, vendor=vendor,
        spec_citation=spec_citation, expected=expected, observed=observed,
        reproducer=reproducer, klass=klass,
        found_at=now.isoformat(timespec="seconds"),
        embargo_until=(now + timedelta(days=days)).isoformat(timespec="seconds"),
        notes=notes,
    )
    d = _store(store)
    path = d / f"{finding.id}.json"
    if path.exists():
        raise DisclosureError(f"{finding.id} already recorded — the same "
                              f"divergence on the same silicon is one finding")
    path.write_text(json.dumps(finding.to_dict(), indent=2) + "\n")
    return finding


def load_all(store: Path | None = None) -> list[Finding]:
    d = store or STORE
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("AUTON-*.json")):
        raw = json.loads(p.read_text())
        raw["klass"] = raw.pop("class")
        out.append(Finding(**raw))
    return out


def set_status(finding_id: str, status: str, dispute: str = "",
               store: Path | None = None) -> Finding:
    if status not in STATUSES:
        raise DisclosureError(f"status must be one of {', '.join(STATUSES)}")
    d = store or STORE
    path = d / f"{finding_id}.json"
    if not path.exists():
        raise DisclosureError(f"no finding {finding_id!r}")
    raw = json.loads(path.read_text())
    raw["status"] = status
    if status == "reported" and not raw.get("reported_at"):
        raw["reported_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if dispute:
        # Recorded alongside, never escalated. A vendor's disagreement is part
        # of the record, not a problem with it.
        raw["dispute"] = dispute
    path.write_text(json.dumps(raw, indent=2) + "\n")
    raw["klass"] = raw.pop("class")
    return Finding(**raw)


def due(within_days: int = 14, store: Path | None = None) -> list[tuple[Finding, int]]:
    """Findings whose embargo has expired or expires soon.

    An embargo nobody tracks quietly becomes permanent, and a finding sat on
    indefinitely is worse for users than one published on schedule.
    """
    now = datetime.now(timezone.utc)
    out = []
    for f in load_all(store):
        if f.status in ("published", "withdrawn"):
            continue
        if not f.embargo_until:
            continue
        remaining = (datetime.fromisoformat(f.embargo_until) - now).days
        if remaining <= within_days:
            out.append((f, remaining))
    return sorted(out, key=lambda x: x[1])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record")
    r.add_argument("--silicon", required=True, help="family:model:stepping[:microcode]")
    r.add_argument("--vendor", required=True)
    r.add_argument("--spec", required=True, dest="spec_citation")
    r.add_argument("--expected", required=True)
    r.add_argument("--observed", required=True)
    r.add_argument("--reproducer", default="")
    r.add_argument("--class", dest="klass", default="semantic", choices=CLASSES)
    r.add_argument("--notes", default="")

    s = sub.add_parser("status")
    s.add_argument("id")
    s.add_argument("state", choices=STATUSES)
    s.add_argument("--dispute", default="")

    sub.add_parser("list")
    d = sub.add_parser("due")
    d.add_argument("--within", type=int, default=14)
    sub.add_parser("contacts")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "record":
            f = record(args.silicon, args.vendor, args.spec_citation, args.expected,
                       args.observed, args.reproducer, args.klass, notes=args.notes)
            print(f"{f.id}  private until {f.embargo_until[:10]}")
            print(f"  contact: {_contacts()[f.vendor]['contact']}")
            return 0
        if args.cmd == "status":
            f = set_status(args.id, args.state, args.dispute)
            print(f"{f.id}: {f.status}")
            return 0
        if args.cmd == "list":
            findings = load_all()
            if not findings:
                print("no findings recorded.")
                return 0
            for f in findings:
                print(f"{f.id}  {f.status:13s} {f.vendor:8s} {f.silicon:16s} "
                      f"embargo to {f.embargo_until[:10]}")
                print(f"  {f.spec_citation}: expected {f.expected!r}, observed {f.observed!r}")
                if f.dispute:
                    print(f"  disputed: {f.dispute}")
            return 0
        if args.cmd == "due":
            rows = due(args.within)
            if not rows:
                print(f"nothing due within {args.within} days.")
                return 0
            for f, remaining in rows:
                when = "EXPIRED" if remaining < 0 else f"{remaining}d"
                print(f"{when:>8s}  {f.id}  {f.vendor}  {f.status}")
            return 1 if any(rem < 0 for _, rem in rows) else 0
        if args.cmd == "contacts":
            for v, c in sorted(_contacts().items()):
                print(f"{v:22s} {c['contact']}")
                print(f"{'':22s} embargo {c.get('embargo_default_days', 90)}d")
            return 0
    except DisclosureError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
