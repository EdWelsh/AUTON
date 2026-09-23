# Report: Errata Table Format (H4)

**Plan**: `.claude/PRPs/plans/w3-hardware-errata-table.plan.md`
**Source PRD**: `auton-hardware-truth.prd.md` — phase 4

## The key mismatch closed itself

H2's report flagged this as *"the next real problem, not the parsing"*: errata applicability is
expressed by **processor line** (ADL-S, ADL-HX, KBL-U), which is a market segment. CPUID does
not report a market segment. H5 captures family/model/stepping. Neither maps onto the other.

The documents close the gap themselves. Every Intel Specification Update carries a **Component
Identification** table giving the exact CPUID signature per line:

```
ADL-S 8+8, ADL-HX 8+8   0x90672   -> family 6, model 151, stepping 2
ADL-S 6+0               0x90675   -> family 6, model 151, stepping 5
ADL-H 6+8, ADL-P 6+8    0x906A3   -> family 6, model 154, stepping 3
ADL-U15W, ADL-U9W       0x906A4   -> family 6, model 154, stepping 4
```

So a line-keyed status becomes a (family, model, stepping)-keyed one, which is exactly what H5
captures. No mapping table to maintain, and nothing guessed.

An independent confirmation fell out of it: `0x90672` folds to family 6 model 151 stepping 2 —
the identical vector `tests/kernel/identity_test.c` pins for Alder Lake-S, derived earlier from
the SDM's folding rules rather than from this table. Two sources, same answer.

## Three-valued, always with a reason

`applies(identity, erratum)` returns `YES | NO | UNKNOWN`, never a bare boolean. Reporting a
vulnerable machine as safe is the failure this PRD exists to avoid; reporting a safe one as
vulnerable destroys trust in every other answer. So:

| situation | verdict |
|---|---|
| The line resolves and its status is known | that status decides |
| No signature in the document matches the identity | **NO** — a confident answer; the document states which parts it covers |
| Every line carries the same status | that status, noting the answer does not depend on the line |
| Lines disagree and the line is unresolved | **UNKNOWN**, saying so |
| The record carries no applicability | **UNKNOWN** |
| **No identification table parsed at all** | never NO — see below |

That last row is the one that matters most. With no signatures, "this document does not cover
your silicon" is unsupportable, and answering NO would mark every erratum inapplicable to every
machine — a clean-looking, entirely false report. Guarded, and tested.

Measured against the real documents:

| identity | against Alder Lake update | against Kaby Lake update |
|---|---|---|
| Alder Lake-S, f6 m151 s2 | 66 YES, 28 NO | 161 NO |
| Alder Lake-P, f6 m154 s3 | 68 YES, 26 NO | 161 NO |
| Kaby Lake S/H/X, f6 m158 | — | 138 YES, 23 NO |
| Skylake, f6 m94 | 94 NO | — |
| AMD Zen 3, f25 m33 | 94 NO | — |

## Two document shapes, again

The parser scored 4 signatures on the first document and **0 on the second**, which silently
degraded every Kaby Lake answer to the weaker "all lines agree" path.

The second document does not print a hex CPUID at all. It gives the bit fields:

```
Table 2. S/H/X-Processor Lines Component Identification
  0000000b 1001b 00b 0110b 1110b xxxxb
```

`ext_model 1001b` + `model 1110b` folds to model 158 — Kaby Lake S/H/X. Same information, a
different encoding. Both are now parsed.

This is the third time in two waves that a parser validated against one document scored zero on
the next. It is not an accident of these files; document shape varies by design, and any
extraction claim from a single example should be read as untested.

Two further bugs found while fixing it:

- **`xxxxb` stepping** means "any stepping". Recorded as `-1`, not `0`, because zero is a real
  stepping and conflating them would make an any-stepping row match only stepping 0.
- **Captions were paired to rows by index** into two separate lists, so one missed caption
  shifted every later pairing — which surfaced as a model-158 signature labelled with the
  Y-line's name. Now paired by position in the document.

## Column matching

The two vocabularies do not match literally. The identification table names a line `ADL-H`; the
errata table heads its column `H/P` because two lines share it; `ADL-U15W` belongs under a
column headed simply `U`. Matching takes the suffix after the family prefix, splits the column
on `/`, and **prefers an exact segment match over a prefix one** — `ADL-HX` must land in `HX`
rather than `H/P`, and both match on prefix alone.

Before this, Alder Lake-P fell through to the weaker path and produced 4 spurious UNKNOWNs.

## Microcode: implemented, unexercised by real data

`Plan Fix` is the status where microcode matters — Intel defines it as *may be fixed in a future
hardware stepping, firmware, or software update*. On a machine whose revision was never read,
whether the fix landed is genuinely unknown, and both YES and NO would be false.

**Neither ingested document uses it.** Both carry only `No Fix`, `Fixed` and `N/A`. The path is
therefore exercised synthetically in tests, and labelled as such — a branch that has never run
is not known to work.

`No Fix` is deliberately independent of microcode: Intel says there are no plans to fix it, so
an unread revision must not turn a confident YES into UNKNOWN.

## Acceptance

- [x] The processor-line vs stepping mismatch resolved in writing — the documents' own
      identification tables close it
- [x] `applies()` returns YES/NO/UNKNOWN with a reason, never a bare boolean
- [x] An unresolvable applicability is UNKNOWN, never NO; absent signature data never yields NO
- [x] An Alder Lake identity matches ADL errata and not KBL ones, in both directions
- [~] **Microcode changes the verdict** — implemented and unit-tested, but no real document
      exercises it. Confirming it needs a Specification Update that uses `Plan Fix`, or the
      Microcode Revision Guidance document, which is inventoried and not yet ingested

## Follow-on

- Ingest `intel-microcode` (Microcode Revision Guidance). Until then, a `Plan Fix` erratum can
  only be UNKNOWN, and the reason says exactly that.
- AMD Revision Guides use a different status vocabulary; `verdict_for` will need extending, and
  an unrecognised status already falls to UNKNOWN rather than being guessed.
- H8 ("is this machine safe?") is now mostly assembly: capture identity, load the tables, report
  the YES set with the UNKNOWN set stated separately rather than folded in.
