# Plan: "Is This Machine Safe?" (H8)

**Source PRD**: `auton-hardware-truth.prd.md` — phase 8
**Depends on**: H5 (landed), H4 (landed), H6
**Note**: the PRD lists H7 as a dependency; H7 needs agents. This delivers the reporting
against whatever mitigations exist, which is the part that does not.

## Summary

The user-facing question. The OS reports **applicable, mitigated, declined, and unmitigatable**
errata for the silicon it is running on — four categories, kept apart.

## Evidence

- H5 captures identity with `IDENT_UNKNOWN` distinct from zero.
- H4 returns YES/NO/UNKNOWN per erratum, never a bare boolean, and refuses to say NO when it
  cannot tell.
- H6 says what a mitigation costs and how to verify it.
- `.claude/PRPs/reports/e2e-intent-scoped-corpus.md`: device facts come from a table, never from
  the model. A safety answer is the same class of fact and must follow the same rule.

## Tasks

### Task 1: The four categories, kept apart
- **Action**: `applicable` (YES, no mitigation), `mitigated` (YES, mitigation applied and
  verified), `declined` (YES, mitigation exists but was not applied — with the reason),
  `unknown` (H4 could not tell). Never collapse `unknown` into either side.
- **Why**: a single "N issues" number is the answer a user will quote, and folding unknowns into
  "safe" is how a vulnerable machine gets reported as fine.
- **Validate**: each category is separately reported and counted.

### Task 2: Answer it from a table
- **Action**: The chat answers `is this machine safe` deterministically, before the model is
  consulted — as `dev.md`'s identity section already specifies for `what cpu is this`.
- **Validate**: the answer matches the table exactly; no model path can produce it.

### Task 3: Say what is not known
- **Action**: The report states its own limits: which documents were ingested, when, and what
  was not checked. A machine with no ingested errata for its silicon reports that, not "safe".
- **Why**: "no known issues" and "no knowledge" are opposite statements that look identical.
- **Validate**: an identity with no matching document reports no-knowledge, never safe.

## Acceptance
- [ ] Four categories reported separately; unknown never folded into safe
- [ ] Answered from the table, before the model
- [ ] An identity with no ingested document reports no-knowledge rather than safe
- [ ] The report states which documents it consulted and when they were retrieved
