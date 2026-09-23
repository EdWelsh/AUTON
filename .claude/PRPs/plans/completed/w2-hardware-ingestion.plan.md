# Plan: Vendor Document Ingestion (H2 + H3)

**Source PRD**: `.claude/PRPs/prds/auton-hardware-truth.prd.md` — phases H2, H3
**Complexity**: Medium, and the quality is uncertain in a way the plan must respect
**Depends on**: H0 (landed), H1 (landed)
**Unblocks**: H4 (errata table format), H8, H10

## Summary

`vendors.yaml` says 43 documents exist. Zero have been fetched or parsed. This plan builds the
ingestion path and points it at the cheapest sources first, deliberately **not** at Intel's
Specification Updates, which are the hardest.

H2 and H3 are planned as one document because the pipeline is shared and the difference is
only which sources it is aimed at.

## Evidence

- `agent/hardware/vendors.yaml` — 28 vendors, 43 documents, 8 redistributable, 7 vendors
  publishing errata at all.
- `.claude/PRPs/reports/w1-hardware-vendor-inventory.md` names the cheap targets in order:
  `arm-sysreg-xml` (XML, redistributable, no PDF parsing), RISC-V specs (source form),
  `pci.ids`/`usb.ids` (flat text).
- `vendor_inventory.py` `fetch_plan()` already refuses a tracked destination for
  non-redistributable documents, and `.cache/` is gitignored.
- The PRD's open question 1: *"Is PDF errata parsing tractable at quality?"* — unanswered, and
  this plan is where it gets answered rather than assumed.
- `agent/kernel_spec/arch/x86_64.md` "Silicon Identity" — the fold is specified and tested, so
  the join key an errata record needs exists.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Fetch refusal | `vendor_inventory.py` `fetch_plan()` | Destination-checked, not intent-checked |
| Provenance | `agent/kernel_spec/reference/README.md` | Record `source_commit`; a derived artifact traces to its source |
| Citation requirement | hardware-truth PRD | document, revision, date, page — an erratum without provenance is a rumour |
| Measured, not assumed | `e2e-intent-scoped-corpus.md` | State the extraction rate; a parser reported as "working" without a number is an assertion |
| Untrusted input | `w0-agent-shell-hardening` | A fetched document is hostile input. Parsing runs with no shell and no network |

## Tasks

### Task 1: The fetch path, offline-testable
- **Action**: `agent/tools/vendor_fetch.py` resolves a document from `vendors.yaml` into
  `.cache/vendor/<vendor>/<id>/`, recording URL, retrieval date, HTTP ETag and SHA-256
  alongside. Re-fetching an unchanged document is a no-op.
- **Critical**: the fetcher must be testable without network. A `--from-file` mode ingests a
  local copy through the identical path, so the parser suite never depends on a vendor's uptime.
- **Validate**: fetching twice produces one copy and one provenance record; `--from-file`
  produces a byte-identical record shape.

### Task 2: Start where parsing is free (H3 first, deliberately)
- **Action**: Ingest in ascending difficulty, and stop to measure at each step:
  1. `pci.ids` / `usb.ids` — flat text, redistributable. Already a solved format.
  2. `arm-sysreg-xml` — the only vendor-published machine-readable register description here.
  3. RISC-V ISA specs — published in source form, so no PDF.
- **Why inverted from the PRD's H2-then-H3 order**: those three need no PDF parsing at all and
  will expose every problem in the *pipeline* — provenance, caching, normalisation, the record
  schema — before the *parser* problem is added on top. Debugging both at once conflates them.
- **Validate**: three sources normalised into one record shape, each carrying full provenance.

### Task 3: Then the hard one, and measure it honestly
- **Action**: One Intel Specification Update and one AMD Revision Guide. Extract the errata
  table: id, title, affected steppings, status, workaround.
- **Report the extraction rate as a number** — rows found versus rows present, counted by hand
  on a sample. The PRD asks whether PDF errata parsing is tractable at quality; the answer is
  this number, and a low one is a finding, not a failure.
- **Gotcha**: an erratum applies to a *stepping range*, and the range is frequently expressed
  as a table of checkmarks per stepping column. A parser that reads the id and title but drops
  the stepping columns has extracted nothing usable — it cannot match a running machine.
- **Validate**: extraction rate stated; a sample of records checked against the source PDF by
  hand; stepping applicability present or the record is rejected.

### Task 4: One record shape, provenance mandatory
- **Action**: Normalised records carry `(vendor, document_id, document_revision, date, page,
  erratum_id, title, applies_to[], status, workaround)`. `applies_to` uses the identity keys
  from `vendors.yaml` — family/model/stepping for x86, implementer/part/variant/revision for
  Arm.
- **Refuse a record without provenance.** An erratum that cannot cite its page is a rumour, and
  a table of rumours is worse than an empty table because it will be trusted.
- **Validate**: a record missing any provenance field is rejected by the schema, with the field
  named.

## Validation

```bash
python agent/tools/vendor_fetch.py --vendor pci-sig --id pci-ids
python agent/tools/vendor_fetch.py --vendor arm --id arm-sysreg-xml
python agent/tools/vendor_ingest.py --vendor intel --id intel-spec-update --report
cd agent && python -m pytest tests/unit/test_vendor_ingest.py -q
git status --porcelain .cache/   # expect empty; .cache is ignored
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| PDF extraction quality is poor | **H** | That is the open question. Task 3 reports a number; a low one redirects the PRD toward vendor-structured sources and away from PDFs |
| Stepping applicability lost | **H** | Explicit validation; a record without it is rejected rather than stored incomplete |
| Licensing violated by automation | **M** | Already a refusal (`fetch_plan`), and `.cache/` is ignored. Task 1 adds no new path |
| A fetched document is hostile input | **M** | Parsing runs with no shell and no network. H0 landed; this is why it was Wave 0 |
| Network flakiness makes the suite unreliable | **M** | `--from-file` means no test needs a vendor to be up |

## Acceptance
- [ ] Fetch records provenance and is idempotent; `--from-file` exercises the identical path
- [ ] Three no-PDF sources ingested and normalised before any PDF is attempted
- [ ] One Intel and one AMD errata document parsed, with the extraction rate **stated as a number**
- [ ] Stepping applicability present in every record, or the record is rejected
- [ ] No record without full provenance; no vendor document committed
