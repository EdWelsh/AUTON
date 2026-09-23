# Plan: H7 Run: Generated F00F Mitigation, Verified (after VMM)

## Summary
w11 closed H7 without a run: F00F `requires: [vmm]`, and no tree had one
(`w11-hardware-generated-mitigations-report.md`). With `w13-generate-mm` supplying a VMM that
implements `vmm_protect` (a 4 KiB permission change inside a 2 MiB mapping), the experiment
becomes askable. This plan runs it under the Generation Experiment Protocol, with the
mitigation's own `verify` as the referee, scored as w11 pre-specified: **steps 1-2 under QEMU can
pass; step 3 is could-not-run-here** unless on a family-5 Pentium.

## User Story
As hardware-truth, I want an agent to implement a mitigation from its spec and have the spec's
own verification decide, so that the registry's `verify` field is shown to be load-bearing.

## Problem → Solution
F00F declined everywhere → a generated IDT remap in a tree with a VMM; `mitigation_registry`
reports it `mitigable` for that tree's slice; verify steps 1-2 checked under QEMU from the
running kernel (`sidt` + a page-table walk); step 3 recorded honestly.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `auton-hardware-truth.prd.md`
- **PRD Phase**: H7
- **Estimated Files**: 3 generated + a verify harness + report
- **Depends on**: `w13-generate-mm` (VMM with `vmm_protect` in a tree), `w12-loop-review-repair`, the protocol in `w13-factory-f6-rerun`

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `.claude/PRPs/reports/w11-hardware-generated-mitigations-report.md` | all | the precondition analysis and Task 4's scoring, fixed in advance |
| P0 | `agent/kernel_spec/mitigations/f00f-idt-remap.md` | all | the spec and its 3-step verify |
| P0 | `agent/tools/mitigation_registry.py` | 128-160 | `assess()` must say `mitigable` for the generated slice |
| P0 | `agent/tools/authorship.yaml` | `f00f-idt-remap` | the H6 row (spec 80, implementation 0) |
| P1 | base `kernel/arch/x86_64/idt.c` | 114-130 | `idt_init`, where the remap goes |

## Patterns to Mirror
### VERIFY_IS_REFEREE
// SOURCE: agent/kernel_spec/mitigations/README.md:24-34: `verify` mandatory and mechanical; a claim not applied is worse than a decline.
### THREE_STATE_VERIFY
// SOURCE: w11 H7 report, Task 4: passed / failed / could-not-run-here, where could-not-run-here is never a pass.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `tests/kernel/f00f_verify.c` (in-kernel verify, human-written before the run) | CREATE | steps 1-2 as a boot-time check: `sidt`, walk to the PTE of the page holding entries 0-6, assert RW=0; markers `[MITIG] f00f idt page read-only`, `[MITIG] f00f step3 could-not-run-here (not family 5)` |
| `<ws>/kernel/arch/x86_64/idt.c` + a `#PF` path | GENERATED | the remap + the PF handler that converts an IDT-fetch fault into `#UD` for the task |
| `agent/tools/authorship.yaml` | UPDATE | an `f00f-idt-remap-generated` experiment row |
| pre-registration + report | CREATE | |

## NOT Building
- Other mitigations. One subject, as pre-registered in w11.
- Running step 3 by emulating a Pentium. QEMU's TCG does not model the locked-bus hang, so it would be a false pass.

## Step-by-Step Tasks
### Task 1: The verify harness (human, before the run)
- **GOTCHA**: `#UD` on a modern CPU for `lock cmpxchg8b <reg>` is *expected* whether or not the remap exists (w11's analysis). The harness therefore executes step 3 only when `family == 5`; otherwise it prints could-not-run-here. Never "passed".
### Task 2: Pre-register, run, archive (protocol)
### Task 3: Referee
- **ORDER**: `mitigation_registry.py --errata intel-pentium-f00f --capabilities <generated slice>` → `mitigable`; build + boot → the two `[MITIG]` markers; a regression check that the normal `#PF` path still works (a deliberate unmapped access in a test build is still reported as `#PF`).
### Task 4: Report against H6 (0 implementation lines), F6 and V8

## Validation Commands
```bash
.venv/bin/python agent/tools/mitigation_registry.py --errata intel-pentium-f00f --capabilities vmm,arch,allocator
scripts/e2e.sh --target <ws> --skip-train     # [MITIG] markers
scripts/measure_authorship.sh --mitigation f00f-idt-remap
```

## Acceptance Criteria
- [ ] Verify steps 1-2 pass under QEMU from inside the running kernel
- [ ] Step 3 recorded could-not-run-here, never pass
- [ ] Normal `#PF` handling unbroken
- [ ] Published beside H6, F6 and V8

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The PF-handler change breaks all page faults | M | H | the regression check in Task 3 |
| Step 3 reported as passed | M | H | the harness cannot print "passed" for step 3 unless family is 5 |


---

## Closed 2026-09-23

Unstarted: F00F needs `vmm_protect`, so it waits on the memory-manager run. The registry, the gates and the scoring rule already exist.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
