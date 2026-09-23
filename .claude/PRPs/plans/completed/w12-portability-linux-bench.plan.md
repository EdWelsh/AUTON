# Plan: Linux Bench on CI, and B1's Ratio Under KVM (windows-linux A1, B1-measurement)

## Summary
A1 (*"`scripts/e2e.sh` green on Linux, artifacts identical in shape to macOS"*) was filed under
"needs a second host". GitHub's `ubuntu-latest` **is** an x86-64 Linux host, already in
`portability.yml`, and it exposes `/dev/kvm`: w11's A2 added the udev rule and a probe step. So
A1 runs there, and so does the measurement half of B1: the same ISO timed under KVM, against the
1.37 s TCG baseline A2 recorded on the M4 Pro. B1's Proxmox confirmation stays with Phase 0
(`w15-portability-proxmox`).

## User Story
As a contributor on Linux, I want the same one-command spine to build and boot AUTON with the
same pass bars as macOS, so that the project is not a one-Mac project; and as B1, I want the
KVM/TCG ratio measured on real KVM rather than asserted.

## Problem → Solution
E2E has only ever run on this Mac; the 10x is a hypothesis → a CI job running
`scripts/e2e.sh --target <kernel-base-v3> --skip-train` and the boot timing under `--accel kvm`
and `--accel tcg` on the same runner; `docs/HOST-MATRIX.md` rows move to "exercised: CI".

## Metadata
- **Complexity**: Medium
- **Source PRD**: `auton-windows-linux.prd.md`
- **PRD Phase**: A1 (complete on CI), B1 (measurement; Proxmox confirmation deferred to Phase 0)
- **Estimated Files**: 5
- **Depends on**: `w12-kernel-base` (e2e needs a tree), A2 (landed)

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `.github/workflows/portability.yml` | all | matrix, the KVM probe step (w11) |
| P0 | `scripts/e2e.sh` | 1-70, 180-200 | stages; `--target`, `--accel`, `--skip-train`; artifacts dir |
| P0 | `scripts/preflight.sh` | all | per-host checks; Linux tool names from `toolchain.sh` |
| P0 | `docs/HOST-MATRIX.md` | all | the rows to update, with "exercised?" honesty |
| P1 | `.claude/PRPs/reports/w11-portability-host-agnostic-entry-report.md` | timing | the TCG baseline and its caveat |
| P1 | scratch `time_boot.sh` in the w11 report's method | — | codify it as `scripts/time-boot.sh` |

## Patterns to Mirror
### CI_ASSERT_RAN
// SOURCE: .github/workflows/portability.yml "Assert the live CPUID check ran (x86 only)": fail if the output shows SKIP.
### ARTIFACT_SHAPE
// SOURCE: scripts/e2e.sh:66-70: `.artifacts/e2e/<RUN_ID>/`.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `scripts/time-boot.sh` | CREATE | boot N times to `[BOOT] OK`, print the per-run seconds, accelerator, QEMU version, CPU model (the w11 scratch script, made permanent) |
| `.github/workflows/portability.yml` | UPDATE | a job `linux-e2e`: apt toolchain (`gcc grub-pc-bin grub-common xorriso qemu-system-x86 mtools`), `scripts/kernel-base.sh`, `preflight.sh`, `e2e.sh --target --skip-train`, `time-boot.sh` under kvm and tcg, upload `.artifacts/e2e` + timings |
| `scripts/e2e.sh` | UPDATE (if needed) | any Linux divergence found; each fix pinned by a CI assertion |
| `docs/HOST-MATRIX.md` | UPDATE | Linux x86_64 row: exercised by CI (run URL), the measured KVM and TCG timings, the ratio, runner CPU; caveat: shared, virtualised runner |
| `agent/tests/unit/test_host_matrix.py` | CREATE | the matrix has an "Exercised?" column and no row says "Yes" without a date/evidence link |

## NOT Building
- Training in CI (`--skip-train`; torch on runners is slow and out of scope).
- A self-hosted runner.

## Step-by-Step Tasks
### Task 1: `time-boot.sh`
- **GOTCHA**: Poll with a timeout. The w11 scratch version spun forever when QEMU exited early. The loop must also check `kill -0`.
### Task 2: The CI job, preflight first
- **GOTCHA**: The e2e rule-engine path needs no torch, but `e2e.sh` stage 0 with `CHECK_E2E=1` checks torch. Run preflight without it, and e2e with `--skip-train`, which must not need a checkpoint. If it does, that is an A1 finding to fix.
### Task 3: Timings under kvm and tcg on the same runner, same ISO
- **VALIDATE**: the job prints `kvm: x.xx s, tcg: y.yy s, ratio: z.z` and fails if the kvm run did not use kvm (`AUTON_ACCEL_REASON` recorded).
### Task 4: Matrix + honesty test

## Validation Commands
```bash
scripts/time-boot.sh <iso> 3
gh workflow run portability.yml && gh run watch
cd agent && ../.venv/bin/python -m pytest tests/unit/test_host_matrix.py -q
```

## Acceptance Criteria
- [ ] `e2e.sh` green on the Linux runner; artifacts in the same shape
- [ ] KVM and TCG timed on the same runner; the ratio recorded with its caveats
- [ ] HOST-MATRIX rows updated with evidence links

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The runner's nested KVM makes the ratio unrepresentative | H | M | stated; Proxmox (Phase 0) is the confirmation |
| The CI minutes cost | L | L | the job runs on `workflow_dispatch` + main only |
