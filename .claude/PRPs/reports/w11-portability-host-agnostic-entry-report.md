# Implementation Report: Host-Agnostic Entry Point (windows-linux A2)

## Summary

Nothing in the scripts chose a QEMU accelerator, so every boot ran on whatever QEMU picked by
default. `auton_accel` now probes and chooses, and both entry points take `--accel`.

**The plan's own preference order would have been wrong on this machine.** It said "Darwin: `hvf`
→ `tcg`". On an Apple Silicon Mac, `qemu-system-x86_64 -accel help` lists **only `tcg`**. HVF
accelerates guests of the host's own architecture, and `-accel hvf` exits with *"invalid
accelerator hvf"*. Selection that trusted `uname -s` would have picked HVF and failed on every
boot. Because this implementation probes QEMU, it reports that TCG is the only option and gives
the reason.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Ask QEMU, do not guess | Complete | `auton_accel_select` is pure, taking (uname, listed, kvm-usable), so every platform branch is tested from this host. `auton_accel` supplies the probed inputs |
| 2 | `--accel` on the entry points | Complete | `e2e.sh` (3 QEMU calls) and `auton-boot.sh`. Precedence is flag > `AUTON_ACCEL` > probe, matching `TARGET`. An explicit unavailable choice exits 2 and names what is available |
| 3 | The three-host matrix | Complete | `docs/HOST-MATRIX.md`. **Only the Apple Silicon row says "Yes"**. Linux is "partly" (CI suites run; the new KVM probe step is wired but not yet observed green) |
| 4 | Preflight names the accelerator | Complete | a NOTE when `tcg`, with what that means for timing; FAIL only when an explicit request can't be met |
| 5 | Timing baseline | Complete | **1.37 / 1.38 / 1.38 s** power-on to `[BOOT] OK`, M4 Pro, TCG, QEMU 11.1.1. One end of B1's ratio, not the ratio |

## Validation

| Check | Result |
|---|---|
| `auton_accel` on this host | `tcg`, with reason: binary lists only tcg, kvm device unusable |
| `scripts/e2e.sh --accel nonesuch` | refused, exit 2: *"it lists: tcg"* |
| `AUTON_ACCEL=kvm scripts/auton-boot.sh` | refused, exit 2 |
| `scripts/preflight.sh` | `NOTE accelerator (tcg)`, ALL PASS |
| `agent/tests/unit/test_accel_select.py` | 12 passed: 7 platform branches, fallback reason, empty list, loud refusal, env honoured, flag beats env |

## Deviations

- **Precedence.** The plan read as "`AUTON_ACCEL` overrides both". I implemented flag > env >
  probe instead, because that is how `e2e.sh` already treats `TARGET` and how every CLI a user
  has met behaves. The env var still beats the probe, which is the `CC` behaviour the plan cited.
- **The baseline ISO** came from `git archive kernel-reference-v1 kernels/x86_64`, extracted into
  a scratch directory outside the repo. `kernels/` stays deleted.
- **CI step added**: the x86 Linux runner installs QEMU, grants `/dev/kvm` through a udev rule,
  and asserts that `kvm` is selected. That runs the real probe on the host class the matrix
  claims. It has **not run yet** because nothing has been pushed.

## Not verified

- Linux, Windows and Intel-Mac selection **on real hosts**. It is tested against synthetic
  inputs only. The matrix says so row by row.
- B1's ratio itself.
- `eval.sh`, `transcript.sh` and `run-acceptance.sh` still call QEMU without `-accel`. They were
  out of the plan's scope, which named the two entry points. They get QEMU's default, which on
  every current host is the same `tcg`.
