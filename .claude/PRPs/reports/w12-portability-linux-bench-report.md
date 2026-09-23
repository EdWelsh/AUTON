# Implementation Report: Linux Bench on CI, and B1's Measurement (A1, B1)

**Plan**: `plans/completed/w12-portability-linux-bench.plan.md`
**Status**: implemented; **the Linux run has not happened**, because this branch cannot be
pushed yet (the active GitHub account lacks access; see the session notes).

## Summary

The `linux-e2e` CI job exists: apt toolchain, CPU torch, `kernel-base.sh`, preflight, the e2e
spine, a check against `docs/E2E-EXPECTED.yaml`, and the same ISO timed under kvm and tcg for
B1's ratio. What landed with it matters more than the job. Running the spine on the named base
**locally** showed it had been red since w10, and why.

## What running the spine found

| Finding | Evidence | Resolution |
|---|---|---|
| **Parity failed with `LOAD FAIL` on every run since w10** | the exporter writes model format v3; `kernel-base-v2`'s loader requires v2 exactly | **`kernel-base-v3`**: a v3 loader (bounds-checked device table, `slm_neural_device_name()`); the script's default; a test pins the loader VERSION to `auton_format.VERSION` |
| On v3 the spine is red at exactly one marker | `[MM] PMM initialized: … total, … reserved, … free`: F3's spec, the base's bump allocator | **correct red**, recorded in `docs/E2E-EXPECTED.yaml` with the plan that clears it (`w13-generate-mm`) |

"Expected red" is a checked fact, not a comment. `scripts/e2e-expect.py` fails on a new failing
marker, on failing at an earlier stage, **and** on a stale expectation: a marker listed as
failing that now passes. 4 tests pin those.

## Tasks

| # | Task | Result |
|---|---|---|
| 1 | `scripts/time-boot.sh` | poll with a limit and `kill -0` (the w11 scratch version spun forever); prints the mean, accelerator, QEMU and CPU. This Mac: 1.38/1.40/1.39 s under tcg |
| 2 | CI job | `linux-e2e` in `portability.yml`: preflight with `CHECK_E2E=1`, e2e rung 3a (trains in CI; parity needs torch), expectation check, kvm vs tcg timing, artifacts uploaded |
| 3 | Timings | recorded for this Mac; the Linux ratio prints when the job first runs |
| 4 | Matrix + honesty test | `docs/HOST-MATRIX.md`: Linux row "Wired, not yet observed"; a new "e2e spine per host" table; `test_host_matrix.py`: "Yes" needs a date, and only this host class says Yes |

## Deviations

- `--skip-train` needs a checkpoint that CI does not have, so the job trains rung 3a (200 steps,
  tiny) with CPU torch, rather than skipping training as the plan assumed.
- A1's success signal ("e2e green on Linux") cannot be *green* on any host until the PMM is
  generated. The honest bar is "matches `E2E-EXPECTED.yaml` on both hosts".
