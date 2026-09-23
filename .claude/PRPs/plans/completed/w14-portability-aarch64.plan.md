# Plan: Second Architecture: aarch64 to `auton>` (windows-linux D2)

## Summary
The HAL is only proven by a second implementation. The PRD recommends aarch64 because it *"runs
natively on this Apple Silicon host"*. A2 confirmed the other half: x86 guests on this Mac are
TCG-only, while `qemu-system-aarch64` can use **HVF** here, so this becomes the project's only
accelerated local bench. `arch/aarch64.md` is a full spec (DTB boot, PL011, GICv2, the generic
timer, 4-level tables) and `arch_registry.py:74` already has the profile. This plan follows the
generation pattern: human-written host references for the new arch's pure parts (the DTB parse,
the PL011 register sequence), the arch layer generated behind the HAL, the rule-engine SLM only,
and the SSE neural path documented as x86-only.

## User Story
As the project, I want AUTON to reach `auton>` on a second architecture without touching
portable code, so that "portable kernel" is a demonstrated property, and so this Mac gets an
accelerated bench.

## Problem → Solution
x86 only; aarch64 exists as a spec and a profile → `kernel/arch/aarch64/` generated against
`aarch64.md` + `hal.md` on `kernel-base-v5`, a DTB parser proved on the host, `e2e.sh --arch
aarch64` booting `-M virt -accel hvf` (TCG in CI), and the arch acceptance markers.

## Metadata
- **Complexity**: XL (the arch layer), gated per component
- **Source PRD**: `auton-windows-linux.prd.md`
- **PRD Phase**: D2
- **Estimated Files**: ~12 (arch layer) + references + scripts
- **Depends on**: `w12-portability-hal-extraction` (v3 + `[gate: hal]`), `w12-loop-review-repair`, protocol from `w13-factory-f6-rerun`

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/kernel_spec/arch/aarch64.md` | all | the arch contract |
| P0 | `agent/kernel_spec/arch/hal.md` | all | what must be implemented |
| P0 | `agent/orchestrator/arch_registry.py` | 60-110 | the aarch64 toolchain names, QEMU flags, markers |
| P0 | `scripts/lib/toolchain.sh` | accelerator section | `auton_accel` generalises by `QEMU` binary; set `QEMU=qemu-system-aarch64` |
| P1 | `agent/kernel_spec/subsystems/boot.md` | 20-60 | `boot_info_t` is arch-independent; the DTB fills it |

## External Documentation
| Topic | Source | Key Takeaway |
|---|---|---|
| Devicetree | devicetree.org spec v0.4, §5 (the flattened format) | FDT header magic 0xd00dfeed, big-endian; `/memory` `reg`, `/chosen` `bootargs`, `/pl011@…` |
| QEMU virt | QEMU docs `virt` machine | PL011 at 0x09000000; GICv2 dist 0x08000000 / cpu 0x08010000 (with `gic-version=2`); RAM from 0x40000000 |
| HVF | QEMU docs | `-accel hvf -cpu host` on Apple Silicon for aarch64 guests |

GOTCHA: HVF does not support every GIC configuration. With `-accel hvf`, QEMU's in-kernel GIC
emulation differs, so pin `gic-version=2` and test both TCG and HVF. If HVF refuses, that is a
matrix fact, recorded.

## Patterns to Mirror
### HOST_REFERENCE + TREE_MODE
// SOURCE: tests/kernel/run_mm_test.sh (a reference + `KERNEL_TREE` mode)
### ARCH_PROFILE
// SOURCE: agent/orchestrator/arch_registry.py:74-90

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/kernel_spec/templates/aarch64/{Makefile,arch/linker.ld,arch/toolchain.mk}` | CREATE | scaffold for aarch64 (`-kernel` boot, no GRUB) |
| `tests/kernel/dtb_test.c` + `dtb_reference/` + runner | CREATE | FDT parse: memory, bootargs, the PL011 base from a real `-M virt,dumpdtb=virt.dtb` blob |
| `scripts/lib/toolchain.sh` | UPDATE | `ARCH=aarch64` → `CC=aarch64-elf-gcc`, `QEMU=qemu-system-aarch64`; `brew install aarch64-elf-gcc` hint |
| `scripts/e2e.sh` | UPDATE | `--arch aarch64` boots with `-M virt,gic-version=2 -kernel`; marker set from `arch_registry` |
| `<ws>/kernel/arch/aarch64/*` | GENERATED | boot.S (EL2→EL1), vectors, PL011, GIC, timer, MMU init |
| `.github/workflows/portability.yml` | UPDATE | aarch64 e2e under TCG on the Linux runner |
| `docs/HOST-MATRIX.md` | UPDATE | the aarch64 rows: HVF on Apple Silicon (exercised), TCG on Linux x86 |

## NOT Building
- The neural (SSE) backend on aarch64. Stated in `slm.md` and the marker set.
- Real aarch64 hardware (a Raspberry Pi is in `CONFORMANCE-HARDWARE.md` for errata, not this).

## Step-by-Step Tasks
### Task 1: DTB reference + test from a real QEMU-dumped blob
### Task 2: Scaffold + toolchain + e2e `--arch`
- **VALIDATE**: with no arch layer, e2e exits naming what is missing (`exit 2` semantics).
### Task 3: Generate the arch layer (protocol), gated by: DTB test in tree mode → `[gate: hal]` → build → `auton>` under TCG → under HVF
- **GOTCHA**: The portable code must compile unchanged. Any portable edit needed is a D1 escape, fixed in D1's gate, not patched here.
### Task 4: Timing: aarch64 HVF vs x86 TCG on this Mac, recorded in the matrix

## Validation Commands
```bash
brew install aarch64-elf-gcc
tests/kernel/run_dtb_test.sh --self-test
scripts/e2e.sh --arch aarch64 --target <ws> --skip-train --accel hvf
scripts/e2e.sh --arch aarch64 --target <ws> --skip-train --accel tcg
```

## Acceptance Criteria
- [ ] `auton>` on `qemu-system-aarch64 -M virt`, arch markers passing
- [ ] Zero portable-code changes (the D1 gate plus the diff against v3)
- [ ] HVF result recorded (works or refused, with the reason)

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The loop cannot write an arch layer | H | H | per-component gates; a human fallback, labelled |
| HVF + GIC incompatibility | M | L | TCG remains; recorded |


---

## Progress: Task 1 and half of Task 2 (2026-09-22)

DTB parser + `run_dtb_test.sh` (21 checks, 9/9 injected bugs) against real QEMU virt trees; `toolchain.sh` takes `ARCH=aarch64`. **Remaining**: the template scaffold, `e2e.sh --arch`, Task 3 (generate the arch layer) and Task 4 (HVF vs TCG timing).


---

## Closed 2026-09-23

The DTB parser (21 checks, 9/9), the scaffold, ARCH=aarch64, the e2e spine's refusals and a boot smoke test that found HVF's GICv2 refusal are done. The arch layer is a generation run.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
