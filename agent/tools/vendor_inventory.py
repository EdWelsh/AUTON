"""Validate the hardware vendor inventory and report coverage.

The inventory says which vendor documents exist, where, under what licence, and
what key their errata are indexed by. This module checks it is well-formed and
reports what is covered — and, more importantly, refuses to produce a fetch plan
that would land a non-redistributable document in a tracked path.

That refusal is the point. Most vendor specifications are freely downloadable
and NOT freely redistributable, which is easy to violate by accident once
ingestion is automated, and tedious to undo afterwards.

    python agent/tools/vendor_inventory.py --validate
    python agent/tools/vendor_inventory.py --coverage
    python agent/tools/vendor_inventory.py --fetch-plan intel --into .cache/vendor
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "agent" / "hardware" / "vendors.yaml"

REQUIRED_VENDOR_FIELDS = ("vendor", "category", "identity_keys")
REQUIRED_DOC_FIELDS = ("id", "title", "kind", "access", "redistributable", "form")

ACCESS_LEVELS = {
    "public-download",
    "public-web",
    "public-source",
    "public-download-after-embargo",
    "registration-required",
    "membership-required",
}

CATEGORIES = {"cpu", "gpu", "soc", "standards"}

# Paths git tracks. A non-redistributable document must never be fetched into
# one of these, and this is checked rather than documented.
TRACKED_PREFIXES = ("agent/", "kernel/", "kernels/", "scripts/", "tests/",
                    "SLM/", "controlplane/", "docs/")


class InventoryError(Exception):
    """Always names the vendor and the document. An inventory of 43 documents
    is not something to bisect by hand."""


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    kind: str
    access: str
    redistributable: bool
    form: str
    vendor: str
    scope: str | None = None
    cadence: str | None = None
    licence: str | None = None
    notes: str | None = None
    doc_number: str | None = None
    url_hint: str | None = None


@dataclass(frozen=True)
class Vendor:
    vendor: str
    category: str
    identity_keys: tuple[str, ...]
    documents: tuple[Document, ...]
    gaps: tuple[dict, ...]


def load(path: Path = INVENTORY) -> tuple[Vendor, ...]:
    if not path.exists():
        raise InventoryError(f"{path}: no inventory")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "vendors" not in data:
        raise InventoryError(f"{path}: top level must be a mapping with 'vendors'")

    seen_vendors: set[str] = set()
    seen_doc_ids: set[str] = set()
    vendors: list[Vendor] = []

    for raw in data["vendors"]:
        for field in REQUIRED_VENDOR_FIELDS:
            if field not in raw:
                raise InventoryError(
                    f"vendor {raw.get('vendor', '<unnamed>')!r}: missing {field!r}"
                )
        name = raw["vendor"]
        if name in seen_vendors:
            raise InventoryError(f"vendor {name!r} appears twice")
        seen_vendors.add(name)

        if raw["category"] not in CATEGORIES:
            raise InventoryError(
                f"vendor {name!r}: category {raw['category']!r} not one of "
                f"{', '.join(sorted(CATEGORIES))}"
            )
        if not raw["identity_keys"]:
            raise InventoryError(
                f"vendor {name!r}: identity_keys is empty. Without it an erratum "
                f"cannot be matched to a running machine, only to a vendor"
            )

        docs: list[Document] = []
        for d in raw.get("documents") or []:
            for field in REQUIRED_DOC_FIELDS:
                if field not in d:
                    raise InventoryError(
                        f"{name}/{d.get('id', '<unnamed>')}: missing {field!r}"
                    )
            if d["id"] in seen_doc_ids:
                raise InventoryError(f"document id {d['id']!r} appears twice")
            seen_doc_ids.add(d["id"])
            if d["access"] not in ACCESS_LEVELS:
                raise InventoryError(
                    f"{name}/{d['id']}: access {d['access']!r} not one of "
                    f"{', '.join(sorted(ACCESS_LEVELS))}"
                )
            if not isinstance(d["redistributable"], bool):
                raise InventoryError(
                    f"{name}/{d['id']}: redistributable must be true or false, "
                    f"got {d['redistributable']!r} — an unclear licence is "
                    f"treated as a blocker, not a default"
                )
            if d["redistributable"] and not d.get("licence"):
                raise InventoryError(
                    f"{name}/{d['id']}: redistributable is true but no licence is "
                    f"named. 'We may redistribute this' needs a reason on record"
                )
            docs.append(Document(
                id=d["id"], title=d["title"], kind=d["kind"], access=d["access"],
                redistributable=d["redistributable"], form=d["form"], vendor=name,
                scope=d.get("scope"), cadence=d.get("cadence"),
                licence=d.get("licence"), notes=d.get("notes"),
                doc_number=d.get("doc_number"), url_hint=d.get("url_hint"),
            ))

        gaps = tuple(raw.get("gaps") or ())
        for g in gaps:
            if "kind" not in g or "reason" not in g:
                raise InventoryError(f"vendor {name!r}: a gap needs 'kind' and 'reason'")

        if not docs and not gaps:
            raise InventoryError(
                f"vendor {name!r}: no documents and no gaps. A vendor with nothing "
                f"available must say so explicitly — silence reads as coverage"
            )

        vendors.append(Vendor(
            vendor=name, category=raw["category"],
            identity_keys=tuple(raw["identity_keys"]),
            documents=tuple(docs), gaps=gaps,
        ))
    return tuple(vendors)


def is_tracked_path(target: str) -> bool:
    """True if `target` is somewhere git tracks.

    A relative destination is resolved against the repo root, never the current
    directory: `.cache/vendor` must mean the same place whether the tool is run
    from the root or from agent/, and resolving against cwd silently turned it
    into `agent/.cache/vendor` — a tracked path that the check then flagged,
    and would have mis-classified the other way just as easily.

    Resolved rather than prefix-matched so `.cache/../agent` cannot sneak past.
    """
    path = Path(target)
    if not path.is_absolute():
        path = ROOT / path
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        return False        # outside the repo entirely
    return str(rel).startswith(TRACKED_PREFIXES) or rel == Path(".")


def fetch_plan(vendor: str, into: str, vendors: tuple[Vendor, ...] | None = None) -> list[dict]:
    """What to fetch for one vendor, into `into`.

    Refuses when `into` is tracked and any document is non-redistributable. The
    check is on the destination, not on intent: a repo full of vendor PDFs is a
    licensing problem whoever added them meant well.
    """
    vendors = vendors if vendors is not None else load()
    match = next((v for v in vendors if v.vendor == vendor), None)
    if match is None:
        raise InventoryError(
            f"unknown vendor {vendor!r}; known: "
            f"{', '.join(sorted(v.vendor for v in vendors))}"
        )
    if not match.documents:
        raise InventoryError(
            f"{vendor!r} has no documents to fetch — "
            f"{'; '.join(g['reason'].strip() for g in match.gaps)}"
        )

    blocked = [d for d in match.documents if not d.redistributable]
    if blocked and is_tracked_path(into):
        raise InventoryError(
            f"refusing to plan a fetch into {into!r}: it is tracked, and "
            f"{len(blocked)} of {vendor}'s documents are not redistributable "
            f"({', '.join(d.id for d in blocked[:3])}). "
            f"Ingest and derive; never vendor the source. Use an untracked "
            f"cache such as .cache/vendor/."
        )

    return [
        {
            "vendor": vendor, "id": d.id, "title": d.title, "form": d.form,
            "access": d.access, "redistributable": d.redistributable,
            "into": str(Path(into) / vendor / d.id),
        }
        for d in match.documents
    ]


def coverage(vendors: tuple[Vendor, ...]) -> str:
    lines: list[str] = []
    by_category: dict[str, list[Vendor]] = {}
    for v in vendors:
        by_category.setdefault(v.category, []).append(v)

    total_docs = sum(len(v.documents) for v in vendors)
    with_errata = [v for v in vendors
                   if any(d.kind == "errata" for d in v.documents)]
    machine_readable = [d for v in vendors for d in v.documents
                        if d.form in ("xml", "c-headers", "flat-text", "pdf+source")]
    redistributable = [d for v in vendors for d in v.documents if d.redistributable]
    no_docs = [v for v in vendors if not v.documents]

    lines.append(f"vendors inventoried : {len(vendors)}")
    lines.append(f"documents           : {total_docs}")
    lines.append(f"  with errata docs  : {len(with_errata)} vendors "
                 f"({', '.join(v.vendor for v in with_errata)})")
    lines.append(f"  machine-readable  : {len(machine_readable)} "
                 f"({', '.join(d.id for d in machine_readable)})")
    lines.append(f"  redistributable   : {len(redistributable)} of {total_docs}")
    lines.append(f"  nothing available : {len(no_docs)} "
                 f"({', '.join(v.vendor for v in no_docs) or 'none'})")
    lines.append("")

    for category in sorted(by_category):
        lines.append(f"[{category}]")
        for v in sorted(by_category[category], key=lambda x: x.vendor):
            kinds = sorted({d.kind for d in v.documents})
            gap_kinds = sorted({g["kind"] for g in v.gaps})
            lines.append(
                f"  {v.vendor:20s} keys={','.join(v.identity_keys):38s} "
                f"docs={len(v.documents)}"
            )
            if kinds:
                lines.append(f"  {'':20s}   has: {', '.join(kinds)}")
            if gap_kinds:
                lines.append(f"  {'':20s}   GAP: {', '.join(gap_kinds)}")
        lines.append("")

    # The distinction the PRD's success metric turns on.
    lines.append("INVENTORIED IS NOT INGESTED.")
    lines.append(f"  inventoried : {len(vendors)} vendors, {total_docs} documents")
    lines.append(f"  ingested    : 0 vendors, 0 documents  (H2/H3 not started)")
    lines.append("  The PRD's '>=6 vendors with an ingestion pipeline' measures the")
    lines.append("  second line, which is zero. This plan delivers the first.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--validate", nargs="?", const=str(INVENTORY), metavar="FILE")
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--fetch-plan", metavar="VENDOR")
    ap.add_argument("--into", default=".cache/vendor")
    args = ap.parse_args(argv)

    try:
        if args.fetch_plan:
            plan = fetch_plan(args.fetch_plan, args.into)
            for item in plan:
                print(f"{item['id']:24s} {item['form']:16s} -> {item['into']}")
            return 0
        vendors = load(Path(args.validate) if args.validate else INVENTORY)
        if args.coverage:
            print(coverage(vendors))
            return 0
        print(f"OK {len(vendors)} vendors, "
              f"{sum(len(v.documents) for v in vendors)} documents")
        return 0
    except InventoryError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
