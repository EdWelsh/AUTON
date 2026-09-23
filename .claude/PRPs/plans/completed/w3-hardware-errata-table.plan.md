# Plan: Errata Table Format (H4)

**Source PRD**: `auton-hardware-truth.prd.md` — phase 4
**Complexity**: Small — the records exist; this is the key and the lookup
**Depends on**: H2 (landed), H5 (landed)
**Unblocks**: H6/H7 (mitigations), H8 ("is this machine safe?")

## Summary

255 errata are normalised and carry applicability. Nothing can look one up for a running
machine. This defines the table's key and the matcher.

The key is the whole problem, and `w2-hardware-ingestion.md` already named why: Intel's Alder
Lake update expresses applicability as **processor lines** (S, H/P, U, HX), not steppings,
while H5 captures **family/model/stepping**. Neither maps cleanly onto the other.

## Evidence

- `agent/tools/vendor_ingest.py` — 255 errata records, each with
  `applies_to: [{line, status}]`.
- `agent/kernel_spec/arch/hal.md` category 8 — `silicon_identity_t` carries vendor, family,
  model, stepping, microcode_rev, each with an `ident_source_t`.
- `.claude/PRPs/reports/w2-hardware-ingestion.md`, Follow-on: *"neither maps cleanly onto the
  family/model/stepping join key H5 captures — that gap is the next real problem, not the
  parsing."*
- `tests/kernel/identity_test.c` — the fold is tested against 8 documented parts, so
  family/model/stepping can be trusted as a key.

## Tasks

### Task 1: Face the key mismatch
- **Action**: Decide and record how a processor-line status becomes a machine-level verdict. The
  honest options: a line→model mapping table (accurate, needs maintenance), or reporting
  applicability as *uncertain* when the document keys on something identity does not capture.
- **Why recorded rather than defaulted**: a wrong answer to "does this erratum apply to me" is
  worse than "I cannot tell", and defaulting to "applies" or "does not apply" both lie.
- **Validate**: a record whose applicability cannot be resolved against an identity is reported
  `UNKNOWN`, never `NO`.

### Task 2: The table and the matcher
- **Action**: `errata_table.py` — load derived records, index by `(vendor, family, model)`,
  and answer `applies(identity, erratum) -> YES | NO | UNKNOWN` with the reason.
- **Validate**: querying with an Alder Lake identity (family 6, model 151) returns the ADL
  errata; querying with a Skylake identity does not.

### Task 3: Microcode is part of the answer
- **Action**: An erratum fixed by a microcode revision is not applicable to a machine carrying
  it. Where the document states one, the matcher must use it; where identity reports
  `IDENT_UNKNOWN`, the verdict is `UNKNOWN`, not `YES`.
- **Validate**: the three cases — patched, unpatched, unknown — produce three distinct verdicts.

## Acceptance
- [ ] The processor-line vs stepping mismatch is resolved in writing, not defaulted
- [ ] `applies()` returns YES/NO/UNKNOWN with a reason, never a bare boolean
- [ ] An unresolvable applicability is UNKNOWN, never NO
- [ ] An Alder Lake identity matches ADL errata and not KBL ones
- [ ] Microcode state changes the verdict, and an unknown revision yields UNKNOWN
