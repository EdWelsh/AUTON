"""Answer "is this machine safe?" for the silicon actually running.

Four categories, kept apart, and a fifth thing that matters more than any of
them: **what is not known.**

    applicable      the erratum applies and nothing addresses it
    mitigable       a mitigation exists and this image can apply it
    declined        a mitigation exists and this image lacks its capabilities
    unmitigatable   no software fix exists (FDIV)
    unknown         H4 could not determine applicability

`unknown` is never folded into safe. "No known issues" and "no knowledge" look
identical in a summary and are opposite statements — a machine for which no
document was ingested is not safe, it is unexamined, and saying otherwise is the
single most damaging thing this tool could do.

Answered from tables, before the model is consulted — the same
retrieval-not-generation rule that governs device facts, for the same reason:
a model asked whether a machine is safe will produce a confident answer.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache" / "vendor"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from errata_table import Identity, Verdict, load as load_errata  # noqa: E402
from mitigation_registry import Assessment, assess, load_all  # noqa: E402


@dataclass
class SafetyReport:
    identity: Identity
    documents: list[dict] = field(default_factory=list)
    assessment: Assessment | None = None
    unknown: list = field(default_factory=list)
    not_applicable: int = 0

    @property
    def examined(self) -> bool:
        """Whether any ingested document covers this silicon at all."""
        return any(d["matched"] for d in self.documents)

    def summary(self) -> str:
        if not self.documents:
            return ("No errata documents have been ingested. This machine has "
                    "not been examined — that is not the same as safe.")
        if not self.examined:
            v = self.identity
            return (f"No ingested document covers {v.vendor} family {v.family} "
                    f"model {v.model}. This machine has not been examined — "
                    f"that is not the same as safe.")
        c = self.assessment.counts() if self.assessment else {}
        parts = []
        if c.get("mitigable"):
            parts.append(f"{c['mitigable']} mitigable")
        if c.get("declined"):
            parts.append(f"{c['declined']} declined")
        if c.get("unmitigatable"):
            parts.append(f"{c['unmitigatable']} unmitigatable")
        if c.get("applicable"):
            parts.append(f"{c['applicable']} with no known mitigation")
        if self.unknown:
            parts.append(f"{len(self.unknown)} undetermined")
        if not parts:
            return "No errata from the ingested documents apply to this machine."
        return "Applicable errata: " + ", ".join(parts) + "."

    def to_json(self) -> str:
        return json.dumps({
            "identity": {
                "vendor": self.identity.vendor, "family": self.identity.family,
                "model": self.identity.model, "stepping": self.identity.stepping,
                "microcode_rev": self.identity.microcode_rev,
            },
            "examined": self.examined,
            "documents": self.documents,
            "counts": (self.assessment.counts() if self.assessment else {}),
            "undetermined": len(self.unknown),
            "not_applicable": self.not_applicable,
            "summary": self.summary(),
        }, indent=2)


def _cached_documents() -> list[Path]:
    if not CACHE.is_dir():
        return []
    out = []
    for prov in sorted(CACHE.rglob("provenance.json")):
        d = json.loads(prov.read_text())
        if d.get("form") == "pdf-tables":
            payload = next((p for p in sorted(prov.parent.iterdir())
                            if p.name != "provenance.json"), None)
            if payload:
                out.append(payload)
    return out


def assess_machine(identity: Identity, image_capabilities: set[str],
                   documents: list[Path] | None = None) -> SafetyReport:
    documents = documents if documents is not None else _cached_documents()
    report = SafetyReport(identity=identity)

    applicable: list[str] = []
    for doc in documents:
        table = load_errata(doc)
        answers = table.query(identity)
        matched = any(a.verdict is not Verdict.NOT_APPLICABLE for a in answers)
        report.documents.append({
            "document": doc.name,
            "errata": len(answers),
            "matched": matched,
            # Stated so a reader can see what the answer rests on, and how old
            # it is. An errata list six months stale reads as current.
            "signatures": len(table.signatures),
        })
        for a in answers:
            if a.verdict is Verdict.APPLIES:
                applicable.append(a.erratum)
            elif a.verdict is Verdict.UNKNOWN:
                report.unknown.append((a.erratum, a.reason))
            else:
                report.not_applicable += 1

    report.assessment = assess(applicable, image_capabilities, load_all())
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vendor", default="GenuineIntel")
    ap.add_argument("--family", type=int, required=True)
    ap.add_argument("--model", type=int, required=True)
    ap.add_argument("--stepping", type=int, default=0)
    ap.add_argument("--microcode", default=None)
    ap.add_argument("--capabilities", default="vmm,arch,allocator,slm")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    identity = Identity(
        args.vendor, args.family, args.model, args.stepping,
        int(args.microcode, 0) if args.microcode else None)
    caps = {t.strip() for t in args.capabilities.split(",") if t.strip()}
    report = assess_machine(identity, caps)

    if args.json:
        print(report.to_json())
        return 0

    print(f"machine: {identity.vendor} family {identity.family} "
          f"model {identity.model} stepping {identity.stepping} "
          f"microcode "
          + (f"0x{identity.microcode_rev:x}" if identity.microcode_rev is not None
             else "unknown"))
    print()
    print(report.summary())
    print()
    if report.documents:
        print("consulted:")
        for d in report.documents:
            print(f"  {d['document']}: {d['errata']} errata, "
                  f"{'covers' if d['matched'] else 'does not cover'} this silicon")
    if report.assessment:
        for label in ("mitigable", "declined", "unmitigatable", "applicable"):
            rows = getattr(report.assessment, label)
            for erratum, m, why in rows[:5]:
                print(f"  [{label}] {erratum}" + (f" -> {m.name}" if m else "")
                      + f" ({why})")
            if len(rows) > 5:
                print(f"  [{label}] ... and {len(rows) - 5} more")
    if report.unknown:
        print(f"  [undetermined] {len(report.unknown)} erratum(s) — "
              f"applicability could not be resolved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
