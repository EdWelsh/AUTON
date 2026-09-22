"""Conformance corpora in, verdicts out (hardware-truth H10).

    python agent/tools/conformance.py --operands build/          # corpus -> inputs
    python agent/tools/conformance.py --summarise build/verdicts.txt
    python agent/tools/conformance.py --summarise build/verdicts.txt --disclose

Two jobs, deliberately both here so the clause citation travels from the corpus
to the verdict without being retyped:

1. **Operands.** Decimal literals in the corpora are turned into bit patterns
   once, in Python, on the host. The C oracle never parses a decimal, because
   `strtod` is host floating point and the whole point of an oracle is that no
   host FP touches the expected answer.

2. **Verdicts.** The harness's output becomes a per-clause summary. A divergence
   on an `architectural` entry is a finding; on a `model-specific` entry it is
   *not assertable*, which is a different sentence and is printed as one.
   `--disclose` routes unexplained architectural divergences to
   `disclosure.record`, citing the clause.

**Zero is a finding.** A clean run prints what was checked and on what silicon,
because a suite that speaks only when it finds something teaches nobody what it
looked at.
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "agent" / "kernel_spec" / "conformance"
REQUIRED_FIELDS = ("id", "clause", "class", "guarantee")
CLASSES = ("semantic", "fault")
GUARANTEES = ("architectural", "model-specific")


class CorpusError(Exception):
    pass


def bits(value) -> int:
    """A decimal (or inf/nan) from the corpus as IEEE 754 binary64 bits."""
    return struct.unpack("<Q", struct.pack("<d", float(value)))[0]


@dataclass
class Entry:
    id: str
    clause: str
    cls: str
    guarantee: str
    raw: dict = field(default_factory=dict)


def load_corpus(directory: Path = CORPUS) -> list[tuple[str, dict, list[Entry]]]:
    out = []
    for path in sorted(directory.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text()) or {}
        entries = []
        seen = set()
        for raw in doc.get("entries", []):
            for f in REQUIRED_FIELDS:
                if not raw.get(f):
                    raise CorpusError(f"{path.name}: an entry lacks {f!r}. "
                                      f"An entry without a clause is an opinion, not a check.")
            if raw["class"] not in CLASSES:
                raise CorpusError(f"{path.name}: {raw['id']}: class {raw['class']!r} "
                                  f"is not one of {CLASSES}")
            if raw["guarantee"] not in GUARANTEES:
                raise CorpusError(f"{path.name}: {raw['id']}: guarantee "
                                  f"{raw['guarantee']!r} is not one of {GUARANTEES}")
            if raw["id"] in seen:
                raise CorpusError(f"{path.name}: duplicate id {raw['id']!r}")
            seen.add(raw["id"])
            entries.append(Entry(raw["id"], raw["clause"], raw["class"],
                                 raw["guarantee"], raw))
        out.append((path.name, doc, entries))
    return out


def write_operands(build: Path, directory: Path = CORPUS) -> tuple[int, int]:
    """Write operands.txt (semantic) and faults.txt (fault). Returns the counts."""
    build.mkdir(parents=True, exist_ok=True)
    semantic, faults = [], []
    for _name, doc, entries in load_corpus(directory):
        op = doc.get("operation", "")
        for e in entries:
            if e.cls == "semantic":
                row = [e.id, op, e.raw.get("rounding", "near_even"),
                       f"{bits(e.raw['a']):016x}"]
                if "b" in e.raw:
                    row.append(f"{bits(e.raw['b']):016x}")
                semantic.append(" ".join(row))
            else:
                faults.append(f"{e.id} {e.raw['bytes']} {e.raw['expect']} {e.guarantee}")
    (build / "operands.txt").write_text("\n".join(semantic) + "\n")
    (build / "faults.txt").write_text("\n".join(faults) + "\n")
    return len(semantic), len(faults)


def clause_of(entry_id: str, directory: Path = CORPUS) -> tuple[str, str, str]:
    """(clause, guarantee, class) for an entry id, or empties when unknown."""
    for _name, _doc, entries in load_corpus(directory):
        for e in entries:
            if e.id == entry_id:
                return e.clause, e.guarantee, e.cls
    return "", "", "semantic"


@dataclass
class Divergence:
    id: str
    clause: str
    cls: str
    expected: str
    observed: str

    @property
    def detail(self) -> str:
        return f"expected {self.expected}, observed {self.observed}"


@dataclass
class Summary:
    checked: int = 0
    diverged: list["Divergence"] = field(default_factory=list)
    not_assertable: list[str] = field(default_factory=list)
    skipped: bool = False
    identity: str = "unknown silicon"


def summarise(text: str, directory: Path = CORPUS) -> Summary:
    s = Summary()
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "IDENTITY":
            s.identity = " ".join(parts[1:])
        elif parts[0] == "OK":
            s.checked += 1
        elif parts[0] == "DIVERGE":
            clause, _guarantee, cls = clause_of(parts[1], directory)
            s.checked += 1
            # semantic: "DIVERGE <id> got <bits> want <bits>"
            # fault:    "DIVERGE <id> wanted <UD|none>, <faulted|executed>"
            rest = parts[2:]
            if len(rest) == 4 and rest[0] == "got" and rest[2] == "want":
                observed, expected = rest[1], rest[3]
            else:
                text = " ".join(rest)
                expected, _, observed = text.partition(",")
                expected = expected.replace("wanted", "").strip()
                observed = observed.strip()
            s.diverged.append(Divergence(parts[1], clause, cls, expected, observed))
        elif parts[0] == "NOT-ASSERTABLE":
            s.checked += 1
            s.not_assertable.append(parts[1])
        elif parts[0].startswith("SKIP"):
            s.skipped = True
    return s


def report(s: Summary) -> str:
    lines = []
    if s.skipped:
        lines.append("SKIPPED on this host: the instructions under test are not native here, "
                     "and running them emulated would measure the emulator.")
    lines.append(f"{len(s.diverged)} divergence(s) across {s.checked} clause-cited checks "
                 f"on {s.identity}")
    for name in s.not_assertable:
        lines.append(f"  not assertable  {name}  (model-specific: reported, never a failure)")
    for d in s.diverged:
        lines.append(f"  DIVERGENCE      {d.id}  {d.detail}"
                     f"\n                  clause: {d.clause}")
    if not s.diverged and not s.skipped:
        lines.append("  Zero is the expected result on a modern part, and is published as a "
                     "finding: the value is the method and the citation trail.")
    return "\n".join(lines)


# CPUID vendor strings to the names contacts.yaml knows. A divergence cannot be
# filed against a vendor nobody has a security contact for, and guessing one is
# worse than refusing.
VENDOR_OF = {"GenuineIntel": "intel", "AuthenticAMD": "amd"}


SILICON_RE = re.compile(r"\b\d+:\d+:\d+(?::\w+)?\b")


def disclose(d: "Divergence", identity: str, store: Path | None = None):
    """File one divergence as a private finding, citing the clause.

    The identity line must carry family:model:stepping — `disclosure.py` refuses
    a vague one, and rightly: "some Intel chips" is not a finding. The harness
    prints it from CPUID (or /proc/cpuinfo) beside the brand string.
    """
    from disclosure import DisclosureError, record

    vendor = next((v for k, v in VENDOR_OF.items() if k in identity), "")
    if not vendor:
        raise DisclosureError(
            f"cannot tell the vendor from the identity {identity!r}. A finding "
            f"is filed against a vendor with a published contact, not against "
            f"an unknown part.")
    match = SILICON_RE.search(identity)
    if not match:
        raise DisclosureError(
            f"the identity {identity!r} carries no family:model:stepping. A "
            f"divergence is filed against a part, not against a brand string.")
    return record(silicon=match.group(0), vendor=vendor, spec_citation=d.clause,
                  expected=d.expected, observed=d.observed,
                  reproducer=f"tests/conformance/run_conformance.sh, entry {d.id}",
                  klass=d.cls, store=store,
                  notes="Generated by agent/tools/conformance.py --disclose.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--operands", type=Path, help="write operands.txt/faults.txt here")
    ap.add_argument("--summarise", type=Path, help="a verdicts file from the harness")
    ap.add_argument("--corpus", type=Path, default=CORPUS)
    ap.add_argument("--disclose", action="store_true",
                    help="route architectural divergences to disclosure.record")
    args = ap.parse_args(argv)

    if args.operands:
        n_sem, n_fault = write_operands(args.operands, args.corpus)
        print(f"{n_sem} semantic operand(s), {n_fault} fault encoding(s) "
              f"-> {args.operands}")
        return 0

    if not args.summarise:
        ap.error("give --operands DIR or --summarise FILE")

    s = summarise(args.summarise.read_text(), args.corpus)
    print(report(s))

    if args.disclose and s.diverged:
        for d in s.diverged:
            disclose(d, s.identity)
        print(f"  {len(s.diverged)} divergence(s) recorded for disclosure")
    return 1 if s.diverged else 0


if __name__ == "__main__":
    raise SystemExit(main())
