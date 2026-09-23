# Report: Vendor Document Ingestion (H2 + H3)

**Plan**: `.claude/PRPs/plans/w2-hardware-ingestion.plan.md`
**Source PRD**: `auton-hardware-truth.prd.md` — phases H2, H3

The inventory said 43 documents exist and zero had been fetched. Four are now ingested, and
the PRD's open question has an answer.

## The open question, answered

> *"Is PDF errata parsing tractable at quality?"* — `auton-hardware-truth.prd.md`, open question 1

**Yes, for Intel Specification Updates**, because they are structured tables rather than prose.
Measured on two real documents:

| Document | pages | table rows | extracted | rate |
|---|---|---|---|---|
| 12th Gen Core (Alder Lake), doc 682436 | 47 | 94 | 94 | **100%** |
| 7th/8th Gen Core, doc 334663 | 67 | 163 | 161 | **98.8%** |

Every record carries applicability — a status per processor line — so it can be matched against
a running machine rather than only against a vendor. A record without it is rejected.

The two misses in the second document are worth naming rather than rounding past:

- **SKL061** is a cross-reference to a *Skylake* erratum inside a *Kaby Lake* document. It was
  never a row here and should not be extracted.
- **KBL062** is a real erratum whose summary row suffered column bleed in the PDF's text layer —
  extracted as `KBL0621`, the id run together with a stepping mark. A source-document artifact,
  not parser logic, and the kind of thing that will recur.

So the parser's true miss is one row in 257 across both documents.

### Two denominators, because only one is a score

The first measurement read 97.6% and was wrong in a way that flattered nothing. `ids_mentioned`
counts every erratum id appearing anywhere, including prose — *"Removed Errata KBL032"*,
*"as described in erratum SKL061"*. Those were never rows. Scoring against them understates the
parser; scoring against table rows measures it. Both numbers are reported, labelled.

## Generalisation was the finding

The parser scored **94/94 on the first document and 0/165 on the second.**

One labels the first column `Erratum ID`, the other just `ID`, and my detection matched on the
header text. A third document will choose a third label.

Detection is now structural: a table is an errata table when any row's first cell matches the
erratum id format. Labels vary; the id format does not. After that change, 100% and 98.8%.

This is the whole reason the plan required two documents. A parser validated against the
document it was written alongside has not been tested, and would have been reported as working.

## Ordering, inverted from the PRD, deliberately

The PRD sequences H2 (Intel/AMD) before H3 (Arm/RISC-V). The plan inverted it: ingest the
sources needing no PDF parsing first, because they expose every problem in the *pipeline* —
provenance, caching, idempotence, the record schema — before the *parser* problem is added on
top. Debugging both at once conflates them.

| Source | form | records |
|---|---|---|
| `pci.ids` (PCI-SIG, v2026.09.15) | flat text | **21,564** devices, 1,011 vendors |
| `usb.ids` (USB-IF, v2026.06.26) | flat text | **20,537** devices |
| RISC-V ISA manual | asciidoc source | confirmed source-form; multi-file include, not assembled |
| Intel Specification Updates ×2 | pdf-tables | **255** errata |

That ordering paid off. Every schema and provenance question was settled on flat text, and when
the PDF arrived the only new problem was the PDF.

## An immediate payoff: AUTON's knowledge base, checked

The registry can be cross-checked against what AUTON hardcodes. All four entries confirmed:

| AUTON's KB | Registry |
|---|---|
| `8086:100e` Intel 82540EM Gigabit Ethernet | Intel Corporation 82540EM Gigabit Ethernet Controller |
| `8086:10d3` Intel 82574L Gigabit Ethernet | Intel Corporation 82574L Gigabit Network Connection |
| `1af4:1000` Virtio network device | Red Hat, Inc. Virtio network device |
| `1af4:1001` Virtio block device | Red Hat, Inc. Virtio block device |

More useful: **two of the three devices AUTON answers "unknown" for are named in the registry.**

| bus device | AUTON today | registry |
|---|---|---|
| `8086:1237` | "Unknown PCI device" | Intel 440FX - 82441FX PMC [Natoma] |
| `8086:7000` | "Unknown PCI device" | Intel 82371SB PIIX3 ISA [Natoma/Triton II] |
| `1234:1111` | "Unknown PCI device" | genuinely absent — QEMU's Bochs VGA id is not in pci.ids |

The honest-miss answers the corpus teaches are honest but no longer necessary for two of them.
That is a direct quality improvement available to the grounding work, and it needs no model
change — it is a table lookup, which is the retrieval-not-generation rule again.

## Provenance is refused, not warned about

Every record carries `(vendor, document_id, document_revision, retrieved_at, sha256)` and
`validate()` raises naming the missing field. An erratum that cannot cite its source is a
rumour, and a table of rumours is worse than an empty table because it will be trusted.

An empty derived file is refused too: an empty file reads as "nothing to report" when it means
"nothing was parsed".

Fetching is idempotent — an unchanged document keeps its original `retrieved_at` rather than
being re-copied — and `--from-file` ingests through the identical path, so no test depends on a
vendor's uptime. All 23 tests run offline.

## Licensing held

- `.cache/` is gitignored; `git status --porcelain .cache/` is empty.
- Zero PDFs tracked, asserted by a test against `git ls-files`.
- Caching a non-redistributable document into a tracked path is refused, tested against a real
  tracked directory.
- Of the four documents ingested, two are redistributable (`pci.ids`, `usb.ids`, GPL/BSD) and
  two are not (the Intel updates). Only derived records could ever be committed.

## Acceptance

- [x] Fetch records provenance and is idempotent; `--from-file` exercises the identical path
- [x] No-PDF sources ingested before any PDF — two fully, RISC-V confirmed as source-form
- [x] One Intel document parsed with the extraction rate **stated as a number** — two, in fact,
      at 100% and 98.8%
- [ ] **An AMD Revision Guide** — not attempted. The Intel result answers the open question, and
      AMD's guides are the same shape (`pdf-tables`); the parser is structural and should carry
      over, but that is a prediction, not a measurement
- [x] Applicability present in every record, or the record is rejected
- [x] No record without full provenance; no vendor document committed

## Follow-on

- AMD Revision Guides next; the structural table detection is the part most likely to carry.
- `applies_to` for Alder Lake is per *processor line* (S, H/P, U, HX), not per stepping number.
  The plan assumed steppings. H4's errata-table key must accommodate both, and neither maps
  cleanly onto the family/model/stepping join key H5 captures — that gap is the next real
  problem, not the parsing.
- The two newly-identifiable bus devices should reach the corpus and the kernel's rule table.
- Column bleed in a PDF text layer (KBL062) will recur. Worth a targeted repair pass that
  re-splits an over-long first cell, rather than accepting a silent one-row loss per document.
