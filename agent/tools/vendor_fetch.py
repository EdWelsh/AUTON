"""Fetch a vendor document into the local cache, with provenance.

`vendors.yaml` says 43 documents exist. This retrieves one and records where it
came from, so anything derived later can cite its source. An erratum that cannot
name its document, revision and page is a rumour, and a table of rumours is
worse than an empty table because it will be trusted.

Documents land in `.cache/vendor/`, which is gitignored. The licensing refusal
lives in `vendor_inventory.fetch_plan()` and is enforced here too: most vendor
specifications are downloadable and not redistributable.

    python agent/tools/vendor_fetch.py --vendor pci-sig --id pci-ids
    python agent/tools/vendor_fetch.py --vendor intel --id intel-sdm --from-file ~/sdm.pdf

`--from-file` ingests a local copy through the identical path. Every parser test
uses it, so no test depends on a vendor's uptime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache" / "vendor"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from vendor_inventory import InventoryError, is_tracked_path, load  # noqa: E402


class FetchError(Exception):
    """Names the vendor and document. A fetch that fails silently leaves a
    half-populated cache that later reads as complete."""


@dataclass(frozen=True)
class Provenance:
    """What a derived record must be able to cite back to."""
    vendor: str
    document_id: str
    title: str
    source: str                 # URL, or "file:<path>"
    retrieved_at: str           # ISO-8601 UTC
    sha256: str
    bytes: int
    form: str
    redistributable: bool
    licence: str | None = None
    doc_number: str | None = None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _find(vendor: str, doc_id: str):
    vendors = load()
    v = next((x for x in vendors if x.vendor == vendor), None)
    if v is None:
        raise FetchError(
            f"unknown vendor {vendor!r}; known: "
            f"{', '.join(sorted(x.vendor for x in vendors))}"
        )
    d = next((x for x in v.documents if x.id == doc_id), None)
    if d is None:
        available = ", ".join(x.id for x in v.documents) or "none"
        gaps = "; ".join(g["reason"].strip() for g in v.gaps)
        raise FetchError(
            f"{vendor!r} has no document {doc_id!r}. Available: {available}."
            + (f" Gaps: {gaps}" if gaps else "")
        )
    return v, d


def destination(vendor: str, doc_id: str, cache: Path = CACHE) -> Path:
    return cache / vendor / doc_id


def fetch(
    vendor: str,
    doc_id: str,
    from_file: str | None = None,
    cache: Path = CACHE,
    force: bool = False,
) -> Provenance:
    """Retrieve one document. Idempotent: an unchanged document is not re-copied.

    Network fetching is not implemented here on purpose. The inventory records
    `url_hint` as a hint rather than identity because URLs rot, and an automated
    fetcher pointed at 43 vendor sites is a maintenance burden that produces
    nothing the parser work needs — `--from-file` covers every test.
    """
    v, d = _find(vendor, doc_id)

    dest_dir = destination(vendor, doc_id, cache)
    if not d.redistributable and is_tracked_path(str(dest_dir)):
        raise FetchError(
            f"refusing to fetch {doc_id!r} into {dest_dir}: it is tracked, and "
            f"the document is not redistributable. Ingest and derive; never "
            f"vendor the source."
        )

    if from_file is None:
        raise FetchError(
            f"{doc_id!r}: no --from-file given and network fetching is not "
            f"implemented. Download it yourself from {d.url_hint or 'the vendor'} "
            f"and pass --from-file. URLs in the inventory are hints, not identity."
        )

    src = Path(from_file).expanduser()
    if not src.is_file():
        raise FetchError(f"--from-file {src}: not a file")

    dest_dir.mkdir(parents=True, exist_ok=True)
    payload = dest_dir / src.name
    record_path = dest_dir / "provenance.json"

    digest = _sha256(src)
    if record_path.exists() and not force:
        existing = json.loads(record_path.read_text())
        if existing.get("sha256") == digest:
            return Provenance(**existing)     # unchanged; no copy

    shutil.copy2(src, payload)
    prov = Provenance(
        vendor=vendor,
        document_id=doc_id,
        title=d.title,
        source=f"file:{src}",
        retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        sha256=digest,
        bytes=payload.stat().st_size,
        form=d.form,
        redistributable=d.redistributable,
        licence=d.licence,
        doc_number=d.doc_number,
    )
    record_path.write_text(json.dumps(asdict(prov), indent=2) + "\n")
    return prov


def cached(cache: Path = CACHE) -> list[Provenance]:
    out = []
    for rec in sorted(cache.rglob("provenance.json")):
        out.append(Provenance(**json.loads(rec.read_text())))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vendor")
    ap.add_argument("--id")
    ap.add_argument("--from-file")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list", action="store_true", help="what is already cached")
    args = ap.parse_args(argv)

    try:
        if args.list:
            records = cached()
            if not records:
                print("nothing cached. INVENTORIED IS NOT INGESTED.")
                return 0
            for p in records:
                print(f"{p.vendor}/{p.document_id:24s} {p.bytes:>10,d} B  "
                      f"{p.sha256[:12]}  {p.retrieved_at}")
            return 0
        if not (args.vendor and args.id):
            ap.error("give --vendor and --id, or --list")
        prov = fetch(args.vendor, args.id, args.from_file, force=args.force)
        print(f"{prov.vendor}/{prov.document_id}: {prov.bytes:,} bytes, "
              f"sha256 {prov.sha256[:16]}")
        print(f"  {destination(prov.vendor, prov.document_id)}")
        return 0
    except (FetchError, InventoryError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
