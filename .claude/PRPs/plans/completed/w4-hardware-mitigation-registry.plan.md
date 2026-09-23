# Plan: Mitigation Registry (H6)

**Source PRD**: `auton-hardware-truth.prd.md` — phase 6
**Depends on**: H4 (landed)
**Unblocks**: H7 (generated mitigations), H8

## Summary

H4 answers *does this erratum apply to this machine*. Nothing says *what to do about it*. A
mitigation registry is mitigations as **spec** — each with a cost and a verification method, so
an image can state what it did and prove it.

## Evidence

- `agent/tools/errata_table.py` returns YES/NO/UNKNOWN per erratum with a reason.
- The PRD's worked example is the **F00F-class IDT remap**: Intel's Pentium F00F bug was
  mitigated by remapping the IDT so the faulting access hit a page the handler owned — a
  software fix for a silicon defect, with a real and measurable cost.
- `agent/kernel_spec/services/README.md` establishes the format shape: front-matter plus prose,
  validated, with every field justified.
- H4's report records that `Plan Fix` errata are UNKNOWN without microcode guidance — a
  mitigation registry is where "apply microcode revision X" becomes a stated action.

## Tasks

### Task 1: The format
- **Action**: `kernel_spec/mitigations/<id>.md` — front-matter naming the errata it addresses,
  the capability it needs, its cost, and **how to verify it was applied**.
- **Why cost is mandatory**: a mitigation with unstated cost gets applied everywhere and
  degrades every image. F00F's remap costs a page and a TLB entry; Spectre-class mitigations
  cost far more.
- **Why verification is mandatory**: an image that claims a mitigation it did not apply is
  worse than one that declines it, and the claim is the part a user acts on.
- **Validate**: the format expresses two structurally different mitigations without new fields.

### Task 2: The worked example
- **Action**: Write the F00F IDT-remap mitigation as the first entry, citing Intel's own
  documentation of the defect.
- **Validate**: implementable from the spec; verification method is mechanical.

### Task 3: Registry and lookup
- **Action**: `mitigation_registry.py` loads them, joins to H4's verdicts, and answers: for this
  identity, which applicable errata have a mitigation, which do not, and what would each cost.
- **Validate**: an Alder Lake identity gets a list; an erratum with no mitigation is reported as
  unmitigated rather than omitted.

## Acceptance
- [ ] The format carries errata, capability, cost and verification, each justified
- [ ] It expresses two structurally different mitigations without new fields
- [ ] The F00F remap is written and implementable
- [ ] Applicable errata with no mitigation are reported, never silently dropped
