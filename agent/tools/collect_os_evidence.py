"""Collect evidence of OS mitigation for each ingested erratum (H12).

    python agent/tools/collect_os_evidence.py --document intel/intel-spec-update \
        --out agent/hardware/os-mitigations.yaml

For every erratum, GitHub code search looks for its id and its exact title in
the Linux and FreeBSD source trees. A hit is recorded as a **candidate** with
its URL, for a person to confirm or reject (a phrase match is not proof of a
mitigation). No hit is recorded as `none-found`, with the query and the date.
Windows has no searchable source and is recorded as `not-checked`, never
`none-found`: absence of evidence from a source nobody searched is not evidence.

Reads documentation and code *locations* only; nothing is copied from either
tree (the PRD's Open Question 2, Linux `bugs.c` licensing).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

SOURCES = (("linux", "torvalds/linux"), ("freebsd", "freebsd/freebsd-src"))
# GitHub code search allows 10 requests a minute.
PACE_SECONDS = 6.5


def search(repo: str, phrase: str) -> list[str]:
    r = subprocess.run(["gh", "search", "code", f'"{phrase}"', "--repo", repo, "--limit", "5",
                        "--json", "path,url"], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"gh search failed for {phrase!r} in {repo}: {r.stderr.strip()}")
    return [h["url"] for h in json.loads(r.stdout or "[]")]


def collect(vendor: str, doc_id: str, existing: dict) -> dict:
    from vendor_ingest import ingest

    records, _ = ingest(vendor, doc_id)
    today = date.today().isoformat()
    out = dict(existing)
    for r in [x for x in records if x.kind == "erratum"]:
        if r.key in out and out[r.key].get("reviewed"):
            continue            # a person already confirmed this entry
        evidence = []
        for os_name, repo in SOURCES:
            hits: list[str] = []
            for phrase in (r.key, r.title):
                hits += search(repo, phrase)
                time.sleep(PACE_SECONDS)
            if hits:
                evidence.append({"os": os_name, "kind": "candidate",
                                 "evidence_url": sorted(set(hits))[0],
                                 "queries": [r.key, r.title], "checked": today})
            else:
                evidence.append({"os": os_name, "kind": "none-found",
                                 "queries": [r.key, r.title], "checked": today})
        evidence.append({"os": "windows", "kind": "not-checked",
                         "why": "no searchable source; KB articles are not indexed by erratum"})
        out[r.key] = {"document": f"{vendor}/{doc_id}", "title": r.title,
                      "vendor_status": r.status, "evidence": evidence}
        print(f"{r.key}: " + ", ".join(f"{e['os']}={e['kind']}" for e in evidence), flush=True)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--document", required=True, help="vendor/doc_id")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    vendor, doc_id = args.document.split("/", 1)
    existing = yaml.safe_load(args.out.read_text()) if args.out.exists() else {}
    data = collect(vendor, doc_id, (existing or {}).get("errata", {}))
    header = ("# Evidence of OS mitigation per erratum, for agent/tools/sweep.py (H12).\n"
              "# Collected by agent/tools/collect_os_evidence.py; `candidate` entries are\n"
              "# confirmed or rejected by a person (reviewed: true). Never copied code.\n")
    args.out.write_text(header + yaml.safe_dump({"errata": data}, sort_keys=True, width=100))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
