"""Answer "does this erratum apply to this machine?" for a captured identity.

255 errata are normalised and carry applicability. Applicability is expressed by
**processor line** — ADL-S, ADL-HX, KBL-U — which is a market segment, not
something CPUID reports. `silicon_identity_t` captures family/model/stepping.
Neither maps onto the other, and that gap was flagged as the next real problem.

It turns out the documents close it themselves. Every Intel Specification Update
carries a "Component Identification" table giving the exact CPUID signature per
processor line:

    ADL-S 8+8, ADL-HX 8+8   0x90672     -> family 6, model 151, stepping 2
    ADL-H 6+8, ADL-P 6+8    0x906A3     -> family 6, model 154, stepping 3

So a line-keyed status becomes a (family, model, stepping)-keyed one, which is
exactly what H5 captures.

The verdict is three-valued and never a bare boolean. A wrong answer to "does
this apply to me" is worse than "I cannot tell" — reporting a vulnerable machine
as safe is the failure this whole PRD exists to avoid, and reporting a safe one
as vulnerable destroys trust in every other answer.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

CPUID_SIG = re.compile(r"0x([0-9A-Fa-f]{5,6})")


class Verdict(str, Enum):
    APPLIES = "YES"
    NOT_APPLICABLE = "NO"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Signature:
    """One CPUID signature and the processor lines that carry it."""
    raw: int
    family: int
    model: int
    stepping: int
    lines: tuple[str, ...]

    @staticmethod
    def from_cpuid(eax: int, lines: tuple[str, ...]) -> "Signature":
        """Folds exactly as arch/x86_64.md specifies. The same rule the kernel
        uses, so a mismatch here is a bug in one of two places rather than a
        third interpretation."""
        base_family = (eax >> 8) & 0xF
        base_model = (eax >> 4) & 0xF
        ext_family = (eax >> 20) & 0xFF
        ext_model = (eax >> 16) & 0xF
        family = base_family + ext_family if base_family == 0xF else base_family
        fold = base_family == 0xF or base_family == 6
        model = base_model + (ext_model << 4) if fold else base_model
        return Signature(eax, family, model, eax & 0xF, lines)


@dataclass
class Identity:
    """The subset of silicon_identity_t a lookup needs."""
    vendor: str
    family: int
    model: int
    stepping: int
    microcode_rev: int | None = None      # None means not read — not zero


@dataclass
class Answer:
    verdict: Verdict
    reason: str
    erratum: str = ""
    status: str | None = None

    def __str__(self) -> str:
        return f"{self.verdict.value}: {self.reason}"


# Some updates give the signature as a hex literal ("0x90672"); others give the
# bit fields directly, with the processor lines in the table caption. Same
# information, two encodings, and a parser that handles one silently degrades
# every answer for the other.
BITFIELD_ROW = re.compile(
    r"([01]{7})b\s+([01]{4})b\s+\S+\s+([01]{4})b\s+([01]{4})b\s+([01x]{4})b")
TABLE_CAPTION = re.compile(r"Table\s+\d+[.:]?\s+(.+?)\s+Component Identification")


def _parse_bitfield_identification(text: str) -> list[Signature]:
    """`0000000b 1001b 00b 0110b 1110b xxxxb` -> family 6, model 158.

    `xxxxb` in the stepping field means "any stepping", which is recorded as
    stepping -1 rather than 0 — zero is a real stepping and conflating the two
    would make an any-stepping row match only stepping 0.
    """
    # Paired by position in the document, not by index into two separate
    # lists. A caption without a row, or a row under a caption the regex missed,
    # silently shifts every later pairing — which showed up as a model-158
    # signature labelled with the Y-line's name.
    out: list[Signature] = []
    events: list[tuple[int, str, object]] = []
    for m in TABLE_CAPTION.finditer(text):
        events.append((m.start(), "caption", m.group(1)))
    for m in BITFIELD_ROW.finditer(text):
        events.append((m.start(), "row", m.groups()))
    events.sort()

    caption = ""
    for _, kind, payload in events:
        if kind == "caption":
            caption = payload
            continue
        ext_family, ext_model, family_code, model_no, stepping = payload
        # "Y/U/U-Quad Core-Processor Lines" -> Y, U
        # "Y/U/U-Quad Core-Processor Lines" -> Y, U
        # "S/H/X-Processor Lines"            -> S, H, X
        # Only the slash-separated run before "-Processor" is the line list;
        # words after it ("Core", "Lines") are prose.
        head = caption.split("-Processor")[0].split(" Core")[0]
        names = tuple(sorted({
            t for t in re.findall(r"[A-Z]{1,3}", head) if t not in ("CPU", "ID")
        }))
        family = int(family_code, 2) + (int(ext_family, 2)
                                        if int(family_code, 2) == 0xF else 0)
        base_model = int(model_no, 2)
        fold = family == 0xF or int(family_code, 2) == 6
        model = base_model + (int(ext_model, 2) << 4) if fold else base_model
        step = -1 if "x" in stepping else int(stepping, 2)
        out.append(Signature(raw=0, family=family, model=model,
                             stepping=step, lines=names))
    return out


def parse_identification_table(pdf_path: Path) -> list[Signature]:
    """Line -> CPUID signature, from the document's own identification table.

    Without this the table can only answer UNKNOWN for every line-keyed
    erratum, because nothing in CPUID reports a market segment.
    """
    import pdfplumber
    import warnings

    warnings.filterwarnings("ignore")
    signatures: list[Signature] = []
    seen: set[int] = set()
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:20]:
            for table in page.extract_tables():
                flat = " ".join((c or "") for row in table for c in row)
                if "Stepping" not in flat or not CPUID_SIG.search(flat):
                    continue
                for row in table:
                    cells = [(c or "").replace("\n", " ").strip() for c in row]
                    if len(cells) < 2:
                        continue
                    m = CPUID_SIG.fullmatch(cells[1]) if cells[1] else None
                    if not m or not cells[0]:
                        continue
                    eax = int(m.group(1), 16)
                    if eax in seen:
                        continue
                    seen.add(eax)
                    # "ADL-S 8+8 ADL-HX 8+8" -> ("ADL-S", "ADL-HX"); the core
                    # counts are packaging, not identity.
                    names = tuple(sorted({
                        t for t in re.findall(r"[A-Z]{2,4}-[A-Z0-9]+", cells[0])
                    }))
                    signatures.append(Signature.from_cpuid(eax, names))

    if not signatures:
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages[:20])
        signatures = _parse_bitfield_identification(text)
    return signatures


def _match_column(lines: list[str], statuses: dict[str, str]) -> tuple[str, str] | None:
    """Pick the applicability column for a processor line.

    The two vocabularies do not match literally. The identification table names
    a line `ADL-H`; the errata table heads its column `H/P` because two lines
    share it. And `ADL-U15W` belongs under a column headed simply `U`.

    So: take the suffix after the family prefix, split the column label on `/`,
    and prefer an exact segment match over a prefix one — `ADL-HX` must land in
    column `HX` rather than in `H/P`, and both would match on prefix alone.
    """
    suffixes = [ln.split("-", 1)[1] if "-" in ln else ln for ln in lines]
    exact: tuple[str, str] | None = None
    prefix: tuple[str, str] | None = None
    for column, status in statuses.items():
        parts = [p.strip() for p in (column or "").split("/") if p.strip()]
        for suffix in suffixes:
            for part in parts:
                if suffix == part and exact is None:
                    exact = (column, status)
                elif suffix.startswith(part) and prefix is None:
                    prefix = (column, status)
    return exact or prefix


@dataclass
class ErrataTable:
    """Errata indexed for lookup by silicon identity."""
    records: list = field(default_factory=list)
    signatures: list[Signature] = field(default_factory=list)

    def _lines_for(self, identity: Identity) -> tuple[list[str], str]:
        """Which processor lines this identity could be, and why."""
        exact = [s for s in self.signatures
                 if s.family == identity.family and s.model == identity.model
                 and s.stepping in (identity.stepping, -1)]
        if exact:
            return [ln for s in exact for ln in s.lines], "exact CPUID signature"
        same_model = [s for s in self.signatures
                      if s.family == identity.family and s.model == identity.model]
        if same_model:
            return [ln for s in same_model for ln in s.lines], "family/model match, stepping differs"
        return [], "no signature in this document matches"

    def applies(self, identity: Identity, erratum) -> Answer:
        """YES / NO / UNKNOWN, always with a reason.

        The logic extracts every bit of available signal without guessing:

        - No signature matches the identity  -> NO. The document does not cover
          this silicon at all, which is a confident answer, not an absence.
        - The matched line's status is known -> that status decides.
        - Every line agrees               -> the answer is line-independent, so
          it holds whatever line this part is.
        - Lines disagree and the line is unresolved -> UNKNOWN. Guessing either
          way is a false statement about a machine.
        """
        statuses = {a["line"]: a["status"] for a in erratum.applies_to}
        if not statuses:
            return Answer(Verdict.UNKNOWN,
                          "the record carries no applicability", erratum.key)

        lines, why = self._lines_for(identity)
        if not lines and self.signatures:
            return Answer(
                Verdict.NOT_APPLICABLE,
                f"no processor in {erratum.document_id} has "
                f"family {identity.family} model {identity.model} "
                f"({why})", erratum.key)

        def verdict_for(status: str) -> tuple[Verdict, str]:
            """Intel's status codes, read literally, with microcode where it
            changes the answer.

            "Plan Fix" is the interesting one: Intel defines it as *may be fixed
            in a future hardware stepping, firmware, or software update*. On a
            machine whose microcode revision was never read, whether the fix
            landed is genuinely unknown — and answering YES there reports a
            possibly-patched machine as vulnerable, while NO reports a
            possibly-vulnerable one as safe. Both are false statements, so the
            answer is UNKNOWN.
            """
            st = status.strip().lower()
            if st == "no fix":
                # Intel: "There are no plans to fix this erratum." Microcode
                # cannot change that, so the verdict does not depend on it.
                return Verdict.APPLIES, "no fix is planned, so microcode state is irrelevant"
            if st == "fixed":
                return Verdict.NOT_APPLICABLE, "fixed in this stepping"
            if st in ("plan fix", "planned fix"):
                if identity.microcode_rev is None:
                    return (Verdict.UNKNOWN,
                            "may be fixed by firmware or software, and this "
                            "machine's microcode revision was not read")
                return (Verdict.UNKNOWN,
                        f"may be fixed by firmware or software; microcode "
                        f"0x{identity.microcode_rev:x} is recorded but no "
                        f"revision guidance is ingested to compare it against")
            if st == "doc":
                return Verdict.NOT_APPLICABLE, "documentation change only"
            if st in ("n/a", ""):
                return Verdict.NOT_APPLICABLE, "does not apply to this line"
            return Verdict.UNKNOWN, f"unrecognised status {status!r}"

        matched = _match_column(lines, statuses)
        if matched:
            line, status = matched
            verdict, note = verdict_for(status)
            return Answer(verdict,
                          f"line {line!r} is {status!r} ({why}); {note}",
                          erratum.key, status)

        distinct = {verdict_for(s)[0] for s in statuses.values()}
        if len(distinct) == 1:
            only = distinct.pop()
            return Answer(only,
                          f"every processor line agrees ({sorted(set(statuses.values()))}), "
                          f"so the answer does not depend on which line this part is",
                          erratum.key)

        return Answer(
            Verdict.UNKNOWN,
            f"applicability varies by processor line "
            f"({sorted(set(statuses.values()))}) and this identity could not be "
            f"resolved to one ({why}). Reporting either way would be a false "
            f"statement about this machine.",
            erratum.key)

    def query(self, identity: Identity) -> list[Answer]:
        return [self.applies(identity, r) for r in self.records]


def load(pdf_path: Path, vendor: str = "intel", doc_id: str = "intel-spec-update") -> ErrataTable:
    from vendor_ingest import _load_provenance, parse_intel_spec_update

    prov, _ = _load_provenance(vendor, doc_id)
    records, _ = parse_intel_spec_update(pdf_path, prov)
    return ErrataTable(records=records, signatures=parse_identification_table(pdf_path))


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--document", required=True, help="a cached spec-update PDF")
    ap.add_argument("--family", type=int, required=True)
    ap.add_argument("--model", type=int, required=True)
    ap.add_argument("--stepping", type=int, default=0)
    ap.add_argument("--vendor", default="GenuineIntel")
    ap.add_argument("--show", type=int, default=6)
    args = ap.parse_args(argv)

    table = load(Path(args.document))
    identity = Identity(args.vendor, args.family, args.model, args.stepping)

    print(f"document signatures: {len(table.signatures)}")
    for s in table.signatures:
        print(f"  0x{s.raw:05X} -> family {s.family} model {s.model} "
              f"stepping {s.stepping}  {', '.join(s.lines)}")
    answers = table.query(identity)
    counts: dict[str, int] = {}
    for a in answers:
        counts[a.verdict.value] = counts.get(a.verdict.value, 0) + 1
    print(f"\nidentity: family {identity.family} model {identity.model} "
          f"stepping {identity.stepping}")
    print(f"  {len(answers)} errata -> " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    for a in answers[:args.show]:
        print(f"    {a.erratum}: {a}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
