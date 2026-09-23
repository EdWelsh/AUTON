# Plan: Vendor Inventory (H1)

**Source PRD**: `.claude/PRPs/prds/auton-hardware-truth.prd.md` — phase H1
**Complexity**: Small — research and data modelling, no agents, no kernel
**Unblocks**: H2/H3 (ingestion), H10 (conformance needs spec sources)

## Summary

The hardware-truth PRD's landscape table is prose. Ingestion needs it machine-readable: per
vendor, which documents exist, where they are, under what licence, at what cadence, and in
what form. This turns that table into a versioned manifest plus a fetch-manifest per vendor,
and records the licensing constraint that shapes everything downstream — most specs are freely
downloadable and **not** freely redistributable.

No fetching happens in this plan. H0 (shell hardening) must land before agents are pointed at
external documents.

## Evidence

- The PRD's landscape section covers CPU/ISA (Intel, AMD, Arm, RISC-V, IBM, SiFive, Loongson),
  GPU (Intel, AMD, NVIDIA), SoC (TI, NXP, ST, Microchip, Broadcom, Rockchip, Allwinner,
  Qualcomm, Apple), and standards bodies (UEFI, USB-IF, PCI-SIG, NVMe, Bluetooth, JEDEC, MIPI,
  SD, IEEE) — as prose, unqueryable.
- `agent/kernel_spec/` has **zero** errata coverage; `grep -ri "errata"` returns only
  incidental CPUID documentation.
- `arch/x86_64.md:1624` documents CPUID leaf `0x1` family/model/stepping — the key every
  vendor errata document is indexed by. The join column exists.
- Existing machine-readable art: `pci.ids`, `usb.ids`, and Linux's `X86_BUG_*` /
  `intel-family.h`.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Registry as data | `pci.ids` / `usb.ids` | Flat, parseable, community-maintained, stable format |
| Errata-to-mitigation mapping | Linux `arch/x86/kernel/cpu/bugs.c`, `asm/cpufeatures.h` | Curated, versioned, keyed to exact families — the closest existing art |
| Provenance discipline | `agent/kernel_spec/reference/README.md` | Records `source_commit` so a derived artifact traces to its source |
| Citation requirement | hardware-truth PRD | Every record carries document, revision, date, page. An erratum without provenance is a rumour |

## Files to Change

| File | Action | Why |
|---|---|---|
| `agent/hardware/vendors.yaml` | CREATE | The machine-readable inventory |
| `agent/hardware/README.md` | CREATE | Licensing constraint, refresh procedure, what must never be vendored |
| `agent/tools/vendor_inventory.py` | CREATE | Validate the manifest; report coverage and staleness |
| `agent/tests/unit/test_vendor_inventory.py` | CREATE | Schema and required-field validation |

## Tasks

### Task 1: Model one vendor entry
- **Action**: Design the record against the hardest case first — Intel, which publishes an
  SDM, per-family Specification Updates, security advisories, and microcode revision guidance,
  each with a different cadence and form:
  ```yaml
  - vendor: intel
    documents:
      - id: intel-sdm
        kind: architecture-manual
        access: public-download
        redistributable: false
        form: pdf
        cadence: quarterly
      - id: intel-spec-update
        kind: errata
        scope: per-family        # keyed on family/model/stepping
        access: public-download
        redistributable: false
        form: pdf-tables
        cadence: monthly
      - id: intel-sa
        kind: security-advisory
        access: public-web
        form: structured
        cadence: continuous
    identity_keys: [family, model, stepping, microcode_rev]
  ```
- **Why Intel first**: if the schema survives Intel it will survive the rest. Designing against
  RISC-V — one open spec, one form — would produce a schema that breaks immediately.
- **Validate**: the same schema expresses Arm (per-core TRMs plus errata notices) and RISC-V
  (open ISA, no central errata) without new fields.

### Task 2: Complete the inventory
- **Action**: Fill in every vendor from the PRD's landscape, honestly marking what is *not*
  available — Apple has no public silicon specs, and that record should say so and point at
  the Asahi Linux documentation as the de-facto reference. PCI-SIG and JEDEC gate base specs
  behind membership while their registries stay public; both facts belong in the record.
- **Why the negatives matter**: a coverage report that silently omits Apple reads as complete.
- **Validate**: every vendor in the PRD appears; each has `access` and `redistributable` set.

### Task 3: Record the licensing constraint as an enforceable rule
- **Action**: `README.md` states the rule — **ingest and derive, never vendor the source
  documents** — and `vendor_inventory.py` refuses to emit a fetch plan for any document whose
  `redistributable` is false into a tracked path.
- **Why**: this constraint is easy to violate accidentally once ingestion is automated, and a
  repo full of vendor PDFs is a licensing problem that is tedious to undo.
- **Validate**: attempting to target a tracked directory for a non-redistributable document is
  refused.

### Task 4: Coverage reporting
- **Action**: `vendor_inventory.py --coverage` reports vendors covered, document kinds per
  vendor, and which identity keys each vendor's errata are indexed by. This is the number the
  PRD's success metric ("≥6 vendors with an ingestion pipeline") is measured against.
- **Validate**: the report distinguishes "inventoried" from "ingested" — this plan delivers
  only the former, and conflating them would overstate progress.

## Validation

```bash
python agent/tools/vendor_inventory.py --validate agent/hardware/vendors.yaml
python agent/tools/vendor_inventory.py --coverage
cd agent && python -m pytest tests/unit/test_vendor_inventory.py -q
# no vendor documents in the repo:
git ls-files | grep -icE '\.pdf$' | grep -q '^0$' && echo "clean"
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| URLs rot | **H** | Record document identity (title, revision, vendor document number) as primary; URL as a hint. A renamed URL must not invalidate a record |
| Licensing violated once fetching is automated | **M** | Task 3 makes it a refusal, not a guideline |
| Inventory read as ingestion | **M** | Task 4 separates the two explicitly in the report |
| Schema fits CPUs and breaks on standards bodies | **M** | Task 1 tests three shapes; add SD/MIPI as a fourth before declaring it done |
| Scope creep into fetching | **M** | H0 gates fetching. This plan produces no network activity |

## Acceptance
- [ ] Every vendor from the PRD landscape is inventoried, negatives included
- [ ] The schema expresses Intel, Arm, RISC-V and a standards body without new fields
- [ ] `redistributable: false` documents cannot be targeted at a tracked path
- [ ] Coverage report distinguishes inventoried from ingested
- [ ] No vendor document is committed to the repo
