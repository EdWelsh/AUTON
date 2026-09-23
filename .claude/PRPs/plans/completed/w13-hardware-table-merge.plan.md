# Plan: Device + Errata Table Merge in the Model File (H13)

## Summary
intent-I put a device table in the model file (format v3, `auton_format.py:42-62`). Errata are
answered on the host (`machine_safety.py`), and a running image cannot answer "is this machine
safe?" from its own data. H13 folds the errata table into the shipped model file beside the
device table. The PRD's Open Question 3 warns that errata change on a vendor's schedule, not a
training schedule, so this plan resolves it: **one versioned section format, carried in a
separate, independently updatable boot module**, keyed by the H5 identity. The device table
stays where it is; the errata section uses the same layout conventions.

## User Story
As a running AUTON image, I want the errata that apply to my silicon available locally, so that
"is this machine safe?" is answered from cited data on the machine itself, updatable without
retraining the model.

## Problem → Solution
Errata live in a host tool → a binary `ERRATA` section (identity key → erratum records with
status, workaround class and citation), built by `build_errata_table.py`, shipped as
`errata.bin` (a module) and read by the kernel's existing lookup path; the model file's version
contract unchanged (v3) because the errata travel separately.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `auton-hardware-truth.prd.md`
- **PRD Phase**: H13 (depends on intent-I, landed)
- **Estimated Files**: 7

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `SLM/tools/auton_format.py` | 1-100 | v3 layout, fixed-width entries + a name pool, binary-searchable in place |
| P0 | `SLM/tools/build_device_table.py`, `SLM/tests/test_device_table.py` | all | the builder + test pattern to mirror |
| P0 | `agent/tools/errata_table.py` | 39-100, 213-330 | `Signature`, `Identity`, `Answer`, the matcher to port |
| P0 | `.claude/PRPs/reports/w10-intent-device-table-report.md` | "scoping" | scope by **target**, not manifest |
| P1 | `agent/kernel_spec/subsystems/slm.md` | model file format section | where the format contract lives |
| P1 | `agent/kernel_spec/subsystems/pkg.md` | Module assets | `pkg_module_asset("errata.bin")` |

## Patterns to Mirror
### FIXED_WIDTH_SECTION
// SOURCE: SLM/tools/auton_format.py:42-62: 12-byte entries, sorted keys, a NUL-separated pool, binary search in place.
### SCOPE_BY_TARGET
// SOURCE: w10 report: 42,101 entries unscoped → 7 for `qemu-pc`.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `SLM/tools/auton_format.py` | UPDATE | an `ERRATA` section spec: header (magic `AERR`, version, source document ids + revisions) + entries keyed `(vendor u8, family u16, model u16, stepping u8)`, sorted, with a record offset; a pool of `{erratum id, status enum, workaround enum, doc idx, page}` + titles |
| `SLM/tools/build_errata_table.py` | CREATE | ingested records → `errata.bin`, scoped by the target's silicon block when present |
| `SLM/tests/test_errata_table_bin.py` | CREATE | round-trip; binary search finds ADL errata for a 682436 signature; an empty table is valid and says "not examined" |
| `agent/tools/package_image.py` | UPDATE | ship `assets/errata.bin` with provenance (document revisions) |
| `agent/kernel_spec/subsystems/slm.md` | UPDATE | REQUIRED: look up by H5 identity; absent module → "not examined, not the same as safe" (the `machine_safety` wording) |
| `tests/kernel/errata_lookup_test.c` + reference | CREATE | the in-kernel lookup over the binary, host-proved |
| `agent/kernel_spec/drivers/README.md` or `slm.md` | UPDATE | the Open Question 3 decision: a separate module, and why |

## NOT Building
- Putting errata inside the tokenizer/weights section (Open Question 3's concern).
- Kernel-side mitigation application (H6/H7).

## Step-by-Step Tasks
### Task 1: Format spec first, with a version and source list in the header
- **GOTCHA**: The identity key must carry the vendor. Intel's and AMD's family/model spaces overlap, and AMD folds the extended *family* where Intel folds the extended *model* (`CONFORMANCE-HARDWARE.md`). Fold before keying, using `identity.c`'s formula.
### Task 2: Builder + round-trip tests
### Task 3: In-kernel lookup reference + host test
### Task 4: Package it
- **VALIDATE**: `PROVENANCE.json` names each source document revision.
### Task 5: Record the decision on Open Question 3

## Validation Commands
```bash
PYTHONPATH=SLM .venv/bin/python -m pytest SLM/tests/test_errata_table_bin.py SLM/tests/test_device_table.py -q
tests/kernel/run_errata_lookup_test.sh --self-test
```

## Acceptance Criteria
- [ ] `errata.bin` built, scoped by target, with cited sources in its header
- [ ] Lookup by folded identity, host-proved
- [ ] Shipped as an independently updatable module; the model file version unchanged
- [ ] "Not examined" preserved when the module is absent

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A stale errata module is trusted | M | M | header revisions shown in the chat answer ("as of <doc rev>") |
| An identity folding mismatch | M | H | reuse `identity.c`'s formula and its test vectors |
