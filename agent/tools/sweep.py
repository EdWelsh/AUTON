"""The unmitigated sweep (hardware-truth H12): documented silicon defects nobody fixes.

    python agent/tools/sweep.py --document intel/intel-spec-update

Every ingested erratum lands in exactly one bucket, each with its evidence:

  vendor-fixed            Intel marks it Fixed (for the covered steppings)
  removed                 the vendor withdrew it (N/A, "Erratum has been removed")
  vendor-workaround       the vendor documents a workaround ("None identified" is not one)
  os-mitigated            a person confirmed an OS mitigation (os-mitigations.yaml, reviewed)
  pending-review          an OS search hit a candidate nobody has confirmed or rejected yet
                          (a rejected hit, `kind: rejected` with its reason, counts as searched)
  documented-unmitigated  No Fix, no vendor workaround, and none found in every OS searched
  not-checked             no evidence collected

`documented-unmitigated` is the headline count, and its wording is exact: none
found in the sources searched, on the date searched. "Not checked" and "checked,
none found" never merge (Windows is always not-checked: no searchable source).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

EVIDENCE = Path(__file__).resolve().parents[1] / "hardware" / "os-mitigations.yaml"
BUCKETS = ("vendor-fixed", "removed", "vendor-workaround", "os-mitigated", "pending-review",
           "documented-unmitigated", "not-checked")
CONFIRMED_KINDS = ("kernel-workaround", "microcode", "documentation-only")


class EvidenceError(Exception):
    pass


@dataclass
class Row:
    key: str
    title: str
    bucket: str
    why: str
    evidence: list[dict] = field(default_factory=list)


def load_evidence(path: Path = EVIDENCE) -> dict:
    if not path.exists():
        return {}
    data = (yaml.safe_load(path.read_text()) or {}).get("errata", {})
    for key, e in data.items():
        for ev in e.get("evidence", []):
            if ev.get("kind") in CONFIRMED_KINDS + ("candidate",) and not ev.get("evidence_url"):
                raise EvidenceError(f"{key}: a {ev['kind']} claim for {ev.get('os')} has no "
                                    f"evidence_url. A mitigation claim without a source is refused.")
    return data


def classify(record, evidence: dict | None) -> Row:
    status = (record.status or "").strip().lower()
    workaround = (record.workaround or "").strip()
    if "erratum has been removed" in (record.title or "").lower() or status == "n/a":
        return Row(record.key, record.title, "removed", "withdrawn by the vendor")
    if status == "fixed":
        return Row(record.key, record.title, "vendor-fixed", "Fixed in the covered steppings")
    if workaround and not workaround.lower().startswith("none identified"):
        return Row(record.key, record.title, "vendor-workaround", workaround[:120])
    if not evidence:
        return Row(record.key, record.title, "not-checked", "no OS evidence collected")
    ev = evidence.get("evidence", [])
    confirmed = [e for e in ev if e.get("kind") in CONFIRMED_KINDS]
    if confirmed:
        return Row(record.key, record.title, "os-mitigated",
                   ", ".join(f"{e['os']}: {e['evidence_url']}" for e in confirmed), ev)
    if any(e.get("kind") == "candidate" for e in ev):
        return Row(record.key, record.title, "pending-review",
                   "an OS search hit needs a person to confirm or reject it", ev)
    # A hit a person reviewed and rejected is a search that found no mitigation.
    searched = [e for e in ev if e.get("kind") in ("none-found", "rejected")]
    if not searched:
        return Row(record.key, record.title, "not-checked", "no OS was searched")
    where = ", ".join(sorted({e["os"] for e in searched}))
    when = max(e.get("checked", "") for e in searched)
    return Row(record.key, record.title, "documented-unmitigated",
               f"No Fix; no vendor workaround; none found in {where} as of {when}", ev)


def sweep(vendor: str, doc_id: str, evidence_path: Path = EVIDENCE) -> list[Row]:
    from vendor_ingest import ingest

    records, _ = ingest(vendor, doc_id)
    evidence = load_evidence(evidence_path)
    return [classify(r, evidence.get(r.key)) for r in records if r.kind == "erratum"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--document", required=True, help="vendor/doc_id")
    ap.add_argument("--list", action="store_true", help="list documented-unmitigated errata")
    args = ap.parse_args(argv)
    vendor, doc_id = args.document.split("/", 1)
    rows = sweep(vendor, doc_id)
    counts = Counter(r.bucket for r in rows)
    print(f"{args.document}: {len(rows)} errata")
    for b in BUCKETS:
        print(f"  {b:<24} {counts.get(b, 0)}")
    unmit = [r for r in rows if r.bucket == "documented-unmitigated"]
    if args.list:
        for r in unmit:
            print(f"  {r.key}  {r.title}  ({r.why})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
