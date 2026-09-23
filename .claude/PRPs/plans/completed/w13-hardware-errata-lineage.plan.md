# Plan: Errata Lineage, Evaluated by Retrodiction (H9)

## Summary
H9 was deferred on a data gap: *"One document is not a lineage."* That is still true. Only Intel
682436 (Alder Lake, 94 errata) is ingested, and the "7th gen" document is inventoried, not
ingested. Intel carries errata across generations, often word for word, so a lineage exists in
the documents; it has simply never been collected. This plan ingests one Intel client lineage
(6th through 14th gen Core spec updates), links recurring errata across generations, assigns
erratum classes, and answers the PRD's own evaluation question (Open Question 5): **can lineage
retrodict?** Hide every document after a date and ask whether lineage pointed at the errata that
followed.

## User Story
As hardware-truth, I want errata linked across silicon generations, so that AUTON can say "this
defect class has recurred in 5 of the last 6 generations" with citations, and so that we know,
by measurement, whether that says anything about the next one.

## Problem → Solution
1 ingested document, no cross-document key → 8+ ingested spec updates, `lineage.py` linking by
normalised title + detail similarity with human-confirmed thresholds, a class taxonomy, and a
retrodiction score published whichever way it falls.

## Metadata
- **Complexity**: Large (mostly data work)
- **Source PRD**: `auton-hardware-truth.prd.md`
- **PRD Phase**: H9
- **Estimated Files**: 6 + documents in the gitignored cache
- **Depends on**: H2, H4 (landed). Independent of the loop, so it can run in w13 alongside generation

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/tools/vendor_ingest.py` | 39-70, 148-257 | `Record` (erratum: key, title, status, workaround, detail, applies_to); the Intel parser |
| P0 | `agent/tools/vendor_fetch.py` | usage | `--from-file`: documents are downloaded by a person and ingested with provenance |
| P0 | `agent/hardware/vendors.yaml` | 40-75 | the Intel errata document entries: add one per generation |
| P0 | `.claude/PRPs/reports/w2-hardware-ingestion.md` | PDF parsing measurements | how reliable the parser is; per-document coverage must be reported |
| P1 | `.claude/PRPs/prds/auton-hardware-truth.prd.md` | Open Questions 1, 5 | parsing tractability; retrodiction |

## External Documentation
| Topic | Source | Key Takeaway |
|---|---|---|
| Intel Specification Updates | intel.com, doc numbers per generation (e.g. 332689 6th gen, 334663 7th, 337346 8th/9th, 615213 10th, …, 682436 12th, 740518 13th/14th) | freely downloadable, not redistributable. Verify each number at download; the list here is a starting point, not a citation |

GOTCHA: verify every document number against the downloaded PDF's own cover. An inventoried
number that is wrong is the phantom-citation defect, one level up.

## Patterns to Mirror
### INGEST_WITH_PROVENANCE
// SOURCE: agent/tools/vendor_ingest.py:57-66 `validate()`: *"A fact that cannot cite its source is a rumour."*
### COVERAGE_REPORTED
// SOURCE: .claude/PRPs/reports/w2-hardware-ingestion.md: parse rates stated per document.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/hardware/vendors.yaml` | UPDATE | one entry per generation's spec update |
| `agent/tools/vendor_ingest.py` | UPDATE (if needed) | layout variants found in older PDFs, each with a fixture test |
| `agent/tools/lineage.py` | CREATE | normalise titles (strip model names, "May", punctuation); pair errata across documents by title similarity + `detail` token Jaccard; output `lineage.json` of chains with every member cited |
| `agent/hardware/erratum-classes.yaml` | CREATE | the class taxonomy (x87/FP, memory ordering, PCIe, power states, performance counters, debug/trace, virtualisation, …), keyword rules + manual overrides |
| `agent/tools/retrodict.py` | CREATE | for cutoff generation g: build lineage from docs < g; predict classes likely in g; score against g's actual errata (precision/recall per class, and "carried-over errata predicted") |
| `agent/tests/unit/test_lineage.py` | CREATE | fixtures from real titles; a threshold pair confirmed by hand; no chain links errata from different vendors |

## NOT Building
- Predicting *specific* new errata. The measurable claim is classes and carry-over.
- AMD or Arm lineage. One vendor's lineage first; the key differs (`CONFORMANCE-HARDWARE.md`).
- Copying anything from Linux `bugs.c` (the PRD's Open Question 2 licensing note).

## Step-by-Step Tasks
### Task 1: Acquire and ingest 8+ generations
- **ACTION**: A person downloads each PDF; `vendor_fetch.py --vendor intel --id <id> --from-file <pdf>`; `vendor_ingest.py` each; record per-document errata count and unparsed pages.
- **VALIDATE**: each document ≥90% of its errata-summary rows parsed, or its coverage stated and the document still used.

### Task 2: Link (lineage)
- **GOTCHA**: Intel renumbers errata per document (`ADL001`, `SKL001`, …). Keys never link across documents; titles and details do. Set thresholds by hand-labelling 50 candidate pairs first, and publish that precision.
- **VALIDATE**: `test_lineage.py`; labelled-pair precision ≥0.9 at the chosen threshold.

### Task 3: Classes
- **VALIDATE**: every erratum gets exactly one class; the "other" class is <15%, or the taxonomy is revised.

### Task 4: Retrodiction, published either way
- **ACTION**: For cutoffs at the 10th, 11th and 12th gen: carry-over prediction (errata in g-1 with status "No Fix" predicted to reappear in g) and class-frequency prediction.
- **VALIDATE**: report precision/recall vs a naive baseline (predict every class at its historical frequency). If lineage does not beat the baseline, **that is the finding**, per the PRD.

### Task 5: Surface in "is this machine safe?"
- **ACTION**: `machine_safety` adds, for an applicable erratum, "recurring since <gen> (N generations)" with citations. Wording states history, not prediction.

## Validation Commands
```bash
.venv/bin/python agent/tools/vendor_ingest.py --vendor intel --id <each>
.venv/bin/python agent/tools/lineage.py --out agent/hardware/derived/lineage.json
.venv/bin/python agent/tools/retrodict.py --cutoff 12
cd agent && ../.venv/bin/python -m pytest tests/unit/test_lineage.py -q
```

## Acceptance Criteria
- [ ] ≥8 Intel client generations ingested with coverage stated
- [ ] Lineage chains cite every member document and page
- [ ] Retrodiction published against a baseline, whichever wins

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Older PDF layouts break the parser | H | M | fixture-per-layout; human extraction for the remainder, stated (Open Question 1's fallback) |
| Lineage links look convincing and are wrong | M | H | hand-labelled precision, published |


---

## Closed 2026-09-23

lineage.py, retrodict.py, the class taxonomy and their tests are done; both refuse below two documents. Blocked on six more spec updates, same download problem.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
