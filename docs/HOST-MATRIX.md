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
| **Linux x86_64** | distro packages, the list in the `linux-e2e` CI job: `gcc clang grub-pc-bin grub-common xorriso qemu-system-x86 mtools` + CPU torch | `kvm` → `tcg`. `kvm` requires `/dev/kvm` readable **and** writable by the user, not just listed by QEMU | **Wired, not yet observed.** The `linux-e2e` job (A1) runs preflight, the e2e spine on `kernel-base-v5` checked against `docs/E2E-EXPECTED.yaml`, and times the same ISO under kvm and tcg (B1). It has not run: this branch has not been pushed |
| **Linux arm64** | distro cross gcc | `tcg` (same reason as Apple Silicon) | **No** |
| **Windows (native, MSYS2/MINGW)** | not established | `whpx` → `tcg` | **No.** No Windows host has run any AUTON script |
| **Windows, WSL2** | as Linux x86_64 | `kvm` if nested virtualisation exposes `/dev/kvm`, else `tcg`. `uname -s` reports `Linux`, so it takes the Linux branch | **No** |

## The control plane per host (C1)

The host half of the chat OS (`controlplane/`). The `controlplane` workflow runs the whole suite
and a per-surface smoke test (`tests/test_platform_smoke.py`) on all three.

| Host | Suite | Terminal | UI (HTTP) | Desktop | Exercised? |
|---|---|---|---|---|---|
| **macOS, Apple Silicon** | 186 passed, 5 skipped | yes | yes | yes, real launch of TextEdit | **Yes** — 2026-09-22, local |
| **Linux (container on this Mac, arm64)** | 178 passed, 13 skipped | yes | yes | **process only**: no `gtk-launch`/`xdg-open` and no session in a container | **Yes** — 2026-09-22, `python:3.12-slim` under Docker on the M4 Pro |
| **Linux x86_64 (a real host)** | — | — | — | — | **Wired**: the matrix job covers it; no x86_64 Linux host has run the control plane |
| **Windows** | — | — | — | — | **No.** No Windows host has run it; the matrix job is wired and needs a push |

What no headless host can prove: that a window actually appeared. The desktop smoke asserts the
launcher's runner executes a real process (on Windows through `cmd /c`, where `start` is a shell
builtin). A real desktop check per OS is still owed, and is what the "Exercised?" column means.

Fixed by running it on Linux: `what oses are running` crashed with `FileNotFoundError` on a host
without a Docker CLI, and two tests assumed the repo layout and a kubectl-without-cluster host.

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

## The e2e spine per host

| Host | Base | Result | Exercised? |
|---|---|---|---|
| Apple Silicon, TCG | `kernel-base-v5` | **RED at markers, as expected**: parity, iso and boot pass; 13/14 markers; the `[MM]` line waits on `w13-generate-mm` (`docs/E2E-EXPECTED.yaml`) | **Yes**, 2026-09-22 |
| Linux x86_64, CI | `kernel-base-v5` | the same expectation, checked by `scripts/e2e-expect.py` | **No**: wired in `linux-e2e`, not yet run |

## Firmware (windows-linux B3)

`scripts/e2e.sh --firmware uefi` (and `auton-boot.sh --firmware uefi`) boots OVMF from pflash,
with the ISO repacked for UEFI by `scripts/iso-efi.sh`. On macOS the EFI GRUB target is a separate
formula (`brew install x86_64-elf-grub`), so the UEFI ISO is UEFI-only there; on Linux,
`grub-mkrescue` with `grub-pc-bin` and `grub-efi-amd64-bin` produces a hybrid.

| Host | BIOS | UEFI (OVMF) | Exercised? |
|---|---|---|---|
| Apple Silicon, TCG | spine matches `E2E-EXPECTED.yaml`; 255 MB RAM on 256M | spine matches the same expectation; 249 MB RAM (OVMF reserves some) | **Yes**, 2026-09-22 |
| Linux x86_64, CI | wired in `linux-e2e` | wired in `linux-e2e` | **No**: not yet run |

Secure Boot is not attempted: the image is unsigned.

## Timing baseline: one end of B1's ratio

| Host | Accelerator | QEMU | ISO | Power-on → `[BOOT] OK` |
|---|---|---|---|---|
| Apple M4 Pro, macOS 26.6 | tcg | 11.1.1 | `kernel-reference-v1`, `make iso` (8.4 MB) | **1.37 s, 1.38 s, 1.38 s** (3 runs) |
| Apple M4 Pro, macOS 26.6 | tcg | 11.1.1 | `kernel-base-v5`, `make iso` | **1.38 s, 1.40 s, 1.39 s**, mean 1.39 s (`scripts/time-boot.sh`, 2026-09-22) |
| GitHub `ubuntu-latest` | kvm and tcg, same ISO | runner's | `kernel-base-v5` | **not yet run.** The `linux-e2e` job prints the ratio |

This is **one point on one machine under one accelerator**. It is not B1's 10x metric and must
not be reported as it. B1 needs the same ISO timed under KVM on an x86 Linux host.

The ISO was built from the tagged reference tree extracted outside the repo
(`git archive kernel-reference-v1 kernels/x86_64`). This project does not contain a kernel, and
the measurement did not put one back.
