"""Build `errata.bin`: precomputed errata verdicts, keyed by silicon identity.

    python SLM/tools/build_errata_table.py --out errata.bin
    python SLM/tools/build_errata_table.py --target agent/kernel_spec/targets/x.md --out e.bin

Every ingested errata document (`.cache/vendor/**`, form `pdf-tables`) is
loaded through `agent/tools/errata_table.py`, and each CPUID signature it covers
gets that module's verdict for every erratum: YES, NO or UNKNOWN, never a guess.
The kernel looks the answers up; it does not re-derive them.

Scoped by **target**, as the device table is (w10): a target's `silicon` block
names one identity, and only that key ships. With no target, every identity the
documents cover ships.

A key the documents do not cover is simply absent. An absent key means **not
examined**, which is not the same as safe (`machine_safety.py`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from errata_format import STATUSES, VENDORS, VERDICTS, Key, Rec, pack  # noqa: E402

PROVENANCE_VENDOR = {"intel": "GenuineIntel", "amd": "AuthenticAMD"}


class BuildError(Exception):
    pass


def documents(cache: Path) -> list[tuple[str, str, Path]]:
    """(vendor, doc_id, pdf) for every ingested errata document."""
    out = []
    if not cache.is_dir():
        return out
    for prov in sorted(cache.rglob("provenance.json")):
        d = json.loads(prov.read_text())
        if d.get("form") != "pdf-tables":
            continue
        payload = next((p for p in sorted(prov.parent.iterdir()) if p.name != "provenance.json"),
                       None)
        if payload:
            out.append((prov.parent.parent.name, prov.parent.name, payload))
    return out


def build(cache: Path, silicon: dict | None = None) -> tuple[list[tuple[str, str]],
                                                           dict[Key, list[Rec]]]:
    from errata_table import Identity, load

    docs: list[tuple[str, str]] = []
    table: dict[Key, list[Rec]] = {}
    for vendor, doc_id, pdf in documents(cache):
        cpu_vendor = PROVENANCE_VENDOR.get(vendor)
        if cpu_vendor is None:
            continue
        t = load(pdf, vendor, doc_id)
        doc_idx = len(docs)
        docs.append((f"{vendor}/{doc_id}", t.records[0].document_revision if t.records else ""))
        for sig in t.signatures:
            key = Key(VENDORS[cpu_vendor], sig.family, sig.model, sig.stepping)
            if silicon and (silicon.get("vendor") != cpu_vendor
                            or (int(silicon["family"]), int(silicon["model"]),
                                int(silicon["stepping"]))
                            != (sig.family, sig.model, sig.stepping)):
                continue
            ident = Identity(cpu_vendor, sig.family, sig.model, sig.stepping)
            recs = table.setdefault(key, [])
            for r in t.records:
                a = t.applies(ident, r)
                recs.append(Rec(f"{r.key}: {r.title}", VERDICTS[a.verdict.value],
                                STATUSES.get((a.status or r.status or "").strip().lower(), 0),
                                doc_idx, int(r.page or 0)))
    return docs, table


def main(argv: list[str] | None = None) -> int:
    from vendor_ingest import CACHE

    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--target", type=Path, help="scope to this target's silicon")
    args = ap.parse_args(argv)

    silicon = None
    if args.target:
        from target_spec import load as load_target
        silicon = load_target(args.target).silicon
    docs, table = build(CACHE, silicon)
    data = pack(docs, table)
    args.out.write_bytes(data)
    n = sum(len(v) for v in table.values())
    print(f"{args.out}: {len(docs)} document(s), {len(table)} identit(ies), {n} verdicts, "
          f"{len(data)} bytes")
    if silicon and not table:
        print("  the target's silicon is covered by no ingested document: not examined")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
