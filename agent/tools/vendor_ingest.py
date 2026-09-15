"""Normalise a cached vendor document into records with provenance.

One record shape for everything: device registries, register descriptions, and
errata. The shape is the point — a consumer keyed on silicon identity should
not care whether a fact came from a flat text registry or a PDF table.

**A record without provenance is refused.** An erratum that cannot cite its
document, revision and page is a rumour, and a table of rumours is worse than
an empty table because it will be trusted.

    python agent/tools/vendor_ingest.py --vendor pci-sig --id pci-ids
    python agent/tools/vendor_ingest.py --all --report
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache" / "vendor"
DERIVED = ROOT / "agent" / "hardware" / "derived"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from vendor_fetch import Provenance, destination  # noqa: E402

PROVENANCE_FIELDS = ("vendor", "document_id", "document_revision", "retrieved_at", "sha256")


class IngestError(Exception):
    pass


@dataclass
class Record:
    """One fact from one document.

    `applies_to` uses the identity keys from vendors.yaml — family/model/stepping
    for x86, implementer/part/variant/revision for Arm — so a record can be
    matched against a running machine rather than only against a vendor.
    """
    kind: str                       # device | register | erratum
    key: str                        # the natural key: "8086:100e", an erratum id
    title: str
    vendor: str
    document_id: str
    document_revision: str
    retrieved_at: str
    sha256: str
    page: int | None = None
    applies_to: list[dict] = field(default_factory=list)
    status: str | None = None
    workaround: str | None = None
    detail: str | None = None

    def validate(self) -> None:
        missing = [f for f in PROVENANCE_FIELDS if not getattr(self, f, None)]
        if missing:
            raise IngestError(
                f"record {self.key!r} lacks provenance: {', '.join(missing)}. "
                f"A fact that cannot cite its source is a rumour."
            )
        if not self.key or not self.title:
            raise IngestError(f"record in {self.document_id!r} has no key or title")


def _load_provenance(vendor: str, doc_id: str) -> tuple[Provenance, Path]:
    d = destination(vendor, doc_id)
    rec = d / "provenance.json"
    if not rec.exists():
        raise IngestError(
            f"{vendor}/{doc_id} is not cached. Fetch it first — "
            f"INVENTORIED IS NOT INGESTED."
        )
    prov = Provenance(**json.loads(rec.read_text()))
    payload = next((p for p in sorted(d.iterdir()) if p.name != "provenance.json"), None)
    if payload is None:
        raise IngestError(f"{vendor}/{doc_id}: provenance but no document")
    return prov, payload


# --- parsers --------------------------------------------------------------- #
# Each returns records. Deliberately separate functions rather than one clever
# dispatcher: the formats have nothing in common, and a shared parser would be
# a pile of conditionals pretending to be an abstraction.

IDS_VENDOR = re.compile(r"^([0-9a-fA-F]{4})\s+(.+)$")
IDS_DEVICE = re.compile(r"^\t([0-9a-fA-F]{4})\s+(.+)$")


def parse_ids_registry(text: str, prov: Provenance) -> list[Record]:
    """`pci.ids` / `usb.ids`: vendor lines, tab-indented device lines.

    Deeper indents are subsystem entries, which are real but not what device
    identification needs, so they are counted and skipped rather than silently
    dropped — the difference matters when reporting an extraction rate.
    """
    revision = "unknown"
    records: list[Record] = []
    current_vendor: tuple[str, str] | None = None
    skipped_subsystems = 0

    for line in text.splitlines():
        if line.startswith("#"):
            m = re.search(r"Version:\s*(\S+)", line)
            if m:
                revision = m.group(1)
            continue
        if not line.strip():
            continue
        if line.startswith("\t\t"):
            skipped_subsystems += 1
            continue
        if (m := IDS_DEVICE.match(line)) and current_vendor:
            vid, vname = current_vendor
            did, dname = m.group(1).lower(), m.group(2).strip()
            records.append(Record(
                kind="device", key=f"{vid}:{did}",
                title=f"{vname} {dname}", vendor=prov.vendor,
                document_id=prov.document_id, document_revision=revision,
                retrieved_at=prov.retrieved_at, sha256=prov.sha256,
                detail=vname,
            ))
            continue
        if m := IDS_VENDOR.match(line):
            current_vendor = (m.group(1).lower(), m.group(2).strip())

    for r in records:
        r.validate()
    return records



# Intel Specification Updates carry an "Errata Summary Table": one row per
# erratum, a status column per processor line or stepping, and a title.
#
# Parsed as a table rather than as text. The text layout interleaves wrapped
# titles with the rows above and below them, and a text parser recovers the ids
# while quietly mangling which title belongs to which — which is worse than
# failing, because the output looks complete.
ERRATUM_ID = re.compile(r"^([A-Z]{2,4}\d{3})$")


def parse_intel_spec_update(path: Path, prov: Provenance) -> tuple[list[Record], dict]:
    """Errata rows from an Intel Specification Update.

    Returns records plus a measurement, because the PRD's open question is
    whether this is tractable *at quality* and the only answer to that is a
    number. `mentioned` counts every erratum id appearing anywhere in the
    document; `extracted` counts those recovered with an applicability column.
    The gap is the honest extraction rate.
    """
    import pdfplumber

    revision = "unknown"
    mentioned: set[str] = set()
    table_row_ids: set[str] = set()
    rows: dict[str, Record] = {}

    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            mentioned.update(ERRATUM_ID.match(t).group(1)
                             for t in re.findall(r"\b[A-Z]{2,4}\d{3}\b", text)
                             if ERRATUM_ID.match(t))
            if revision == "unknown":
                m = re.search(r"Document Number:?\s*(\d{6})", text) or \
                    re.search(r"Revision\s+(\d{3})\b", text)
                if m:
                    revision = m.group(1)

            for table in page.extract_tables():
                if not table:
                    continue
                for row in table[1:]:
                    if row and ERRATUM_ID.match((row[0] or "").strip()):
                        table_row_ids.add((row[0] or "").strip())
                if len(table[0]) < 3:
                    continue      # detail section, not the summary table
                # Detected by row shape, not by header text. One document
                # labels the first column "Erratum ID" and another just "ID";
                # a third will choose something else. What does not vary is a
                # first cell matching the erratum id format, so that is the
                # test. Matching on labels extracted 94/94 from one document
                # and 0/165 from the next.
                if not any(ERRATUM_ID.match((row[0] or "").strip())
                           for row in table[1:] if row):
                    continue
                header = [(c or "").strip() for c in table[0]]
                # The column labels sit on the second row when the header spans
                # ("Processor Line" over S / H/P / U / HX).
                labels = [(c or "").strip() for c in table[1]] if len(table) > 1 else []
                applies_labels = labels[1:-1] if labels and not ERRATUM_ID.match(labels[0] or "") else []

                for row in table[1:]:
                    cells = [(c or "").replace("\n", " ").strip() for c in row]
                    if not cells or not ERRATUM_ID.match(cells[0]):
                        continue
                    erratum_id = cells[0]
                    table_row_ids.add(erratum_id)
                    title = cells[-1]
                    statuses = cells[1:-1]
                    applies = [
                        {"line": applies_labels[i] if i < len(applies_labels) else f"col{i}",
                         "status": st}
                        for i, st in enumerate(statuses) if st
                    ]
                    if erratum_id in rows:
                        continue
                    rows[erratum_id] = Record(
                        kind="erratum", key=erratum_id, title=title or "(no title)",
                        vendor=prov.vendor, document_id=prov.document_id,
                        document_revision=revision, retrieved_at=prov.retrieved_at,
                        sha256=prov.sha256, page=page_no,
                        applies_to=applies,
                        status=statuses[0] if statuses else None,
                    )

    records = list(rows.values())
    # A record without applicability cannot be matched to a running machine. It
    # is an erratum belonging to *a vendor*, which is not what anyone asked.
    usable = [r for r in records if r.applies_to]
    rejected = [r.key for r in records if not r.applies_to]
    for r in usable:
        r.validate()

    # Two denominators, because they answer different questions and only one of
    # them is a parser score.
    #
    # `ids_mentioned` counts every id appearing anywhere, which includes prose:
    # "Removed Errata KBL032", "as described in erratum SKL061" (a cross-
    # reference to a *different* processor's document). Those are not rows and
    # were never extractable, so scoring against them understates the parser.
    #
    # `table_rows_seen` counts ids found as the first cell of a table row —
    # the actual population. The gap between that and `with_applicability` is
    # the parser's real miss rate.
    unextracted = sorted(mentioned - set(rows))
    measurement = {
        "ids_mentioned": len(mentioned),
        "table_rows_seen": len(table_row_ids),
        "with_applicability": len(usable),
        "rejected_no_applicability": rejected,
        "not_extracted": unextracted,
        "extraction_rate": (round(100.0 * len(usable) / len(table_row_ids), 1)
                            if table_row_ids else 0.0),
        "mention_rate": (round(100.0 * len(usable) / len(mentioned), 1)
                         if mentioned else 0.0),
    }
    return usable, measurement


def ingest(vendor: str, doc_id: str) -> tuple[list[Record], dict]:
    prov, payload = _load_provenance(vendor, doc_id)
    text = ("" if prov.form.startswith("pdf")
            else payload.read_text(encoding="utf-8", errors="replace"))

    measurement: dict = {}
    if prov.form == "flat-text":
        records = parse_ids_registry(text, prov)
    elif prov.form == "pdf-tables":
        records, measurement = parse_intel_spec_update(payload, prov)
    else:
        raise IngestError(
            f"{vendor}/{doc_id}: no parser for form {prov.form!r}. "
            f"Parsers exist for: flat-text, pdf-tables."
        )

    report = {
        "vendor": vendor, "document_id": doc_id,
        "document_revision": records[0].document_revision if records else "unknown",
        "records": len(records),
        "source_bytes": prov.bytes,
        "sha256": prov.sha256[:16],
    }
    report.update(measurement)
    return records, report


def write_derived(records: list[Record], out_dir: Path = DERIVED) -> Path:
    """Derived records may be committed; the source documents may not."""
    if not records:
        raise IngestError("refusing to write an empty derived file")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{records[0].vendor}-{records[0].document_id}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(asdict(r), separators=(",", ":")) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vendor")
    ap.add_argument("--id")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--write", action="store_true", help="write derived records")
    ap.add_argument("--sample", type=int, default=0)
    args = ap.parse_args(argv)

    targets = []
    if args.all:
        for rec in sorted(CACHE.rglob("provenance.json")):
            p = Provenance(**json.loads(rec.read_text()))
            targets.append((p.vendor, p.document_id))
    elif args.vendor and args.id:
        targets = [(args.vendor, args.id)]
    else:
        ap.error("give --vendor and --id, or --all")

    rc = 0
    for vendor, doc_id in targets:
        try:
            records, report = ingest(vendor, doc_id)
        except IngestError as exc:
            print(f"FAILED {vendor}/{doc_id}: {exc}", file=sys.stderr)
            rc = 1
            continue
        print(" ".join(f"{k}={v}" for k, v in report.items()))
        for r in records[:args.sample]:
            print(f"    {r.key}  {r.title[:70]}")
        if args.write:
            print(f"    -> {write_derived(records).relative_to(ROOT)}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
