# Host Matrix

What each host AUTON builds and boots on uses, what it can verify, and **what it cannot**.
Consumed by windows-linux A1 (Linux bench), A3 (Windows), B1 (the KVM-vs-TCG ratio) and C1.
Hand this file to whoever sets up a second machine.

**Read the "Exercised?" column first.** Only one row has been run by a person. A matrix that
looks uniformly verified when most of it is untested is worse than no matrix.

## The matrix

| Host | Toolchain source | Accelerator (selected by probe) | Exercised? |
|---|---|---|---|
| **macOS, Apple Silicon** (arm64) | Homebrew: `x86_64-elf-gcc`, `i686-elf-grub`, `qemu` — `scripts/lib/toolchain.sh` | **`tcg` only.** HVF accelerates guests of the host's own architecture; `qemu-system-x86_64` on arm64 lists nothing else | **Yes** — M4 Pro, QEMU 11.1.1, 2026-09-21 |
| **macOS, Intel** (x86_64) | Homebrew, as above | `hvf` → `tcg` | **No.** Written from QEMU's documentation |
| **Linux x86_64** | distro `gcc`, `grub-mkrescue`, `qemu-system-x86` | `kvm` → `tcg`. `kvm` requires `/dev/kvm` readable **and** writable by the user, not just listed by QEMU | **Partly.** Unit suites and identity/allocator self-tests run in CI (`.github/workflows/portability.yml`). The KVM probe step is wired but **not yet observed green**. No boot has been run |
| **Linux arm64** | distro cross gcc | `tcg` (same reason as Apple Silicon) | **No** |
| **Windows (native, MSYS2/MINGW)** | not established | `whpx` → `tcg` | **No.** No Windows host has run any AUTON script |
| **Windows, WSL2** | as Linux x86_64 | `kvm` if nested virtualisation exposes `/dev/kvm`, else `tcg`. `uname -s` reports `Linux`, so it takes the Linux branch | **No** |

## Verifiable per host

| Check | Apple Silicon | x86_64 Linux | Why it differs |
|---|---|---|---|
| Build an x86_64 ISO | yes | yes | cross toolchain on the Mac, native on Linux |
| Boot it | yes, emulated | yes, accelerated with KVM | foreign vs native ISA |
| Live CPUID cross-check (`tests/kernel/run_identity_test.sh`) | **no, prints SKIP** | yes, and CI asserts it did not skip | needs x86 silicon |
| Silicon-divergence conformance (hardware-truth H10) | **no** | **no, under QEMU either way** | QEMU implements an idealised CPU. It needs bare metal, see `agent/hardware/CONFORMANCE-HARDWARE.md` |
| Boot timing comparable to B1's KVM figure | one end only | the other end | B1 is a ratio and needs both |

## Selecting the accelerator

```bash
source scripts/lib/toolchain.sh && auton_accel && echo "$AUTON_ACCEL — $AUTON_ACCEL_REASON"
scripts/preflight.sh                  # names it; tcg is a NOTE, not a FAIL
scripts/e2e.sh --accel tcg            # explicit
AUTON_ACCEL=kvm scripts/auton-boot.sh # environment; an explicit flag still wins over it
```

The probe asks QEMU (`-accel help`) and checks `/dev/kvm` itself. It does not infer the
accelerator from `uname`. An explicit request the host cannot honour **fails, naming what is
available**. It never quietly downgrades to TCG, because a run that asked for KVM and got TCG is
~10x slower and reads as a regression.

## Timing baseline: one end of B1's ratio

| Host | Accelerator | QEMU | ISO | Power-on → `[BOOT] OK` |
|---|---|---|---|---|
| Apple M4 Pro, macOS 26.6 | tcg | 11.1.1 | `kernel-reference-v1`, `make iso` (8.4 MB) | **1.37 s, 1.38 s, 1.38 s** (3 runs) |

This is **one point on one machine under one accelerator**. It is not B1's 10x metric and must
not be reported as it. B1 needs the same ISO timed under KVM on an x86 Linux host.

The ISO was built from the tagged reference tree extracted outside the repo
(`git archive kernel-reference-v1 kernels/x86_64`). This project does not contain a kernel, and
the measurement did not put one back.
