# Plan: UEFI Boot Path under OVMF (windows-linux B3)

## Summary
Every AUTON image boots through GRUB's BIOS target (`i386-pc`): the base Makefile runs
`grub-mkrescue` over `grub/grub.cfg` with no EFI config. Hardware made after about 2015 often
disables CSM, so metal (B4) needs UEFI first. This plan adds an `x86_64-efi` GRUB target
producing a hybrid ISO, boots it under QEMU with OVMF (`edk2-x86_64-code.fd` ships with Homebrew
QEMU), and verifies the Multiboot2 handoff (`boot_info`) survives. Under EFI, GRUB passes the EFI
memory map and system table tags, and the legacy framebuffer and ACPI discovery paths differ.

## User Story
As whoever boots AUTON on a modern PC, I want the ISO to boot under UEFI, so that a machine
without CSM can run it at all.

## Problem → Solution
BIOS-only ISO → a hybrid BIOS+UEFI ISO (`grub-mkrescue` with both platform dirs), a
`grub-efi.cfg`, `e2e.sh --firmware uefi` booting via `-drive if=pflash,…edk2-x86_64-code.fd`, and
a boot_info test proving the EFI-specific Multiboot2 tags parse (type 17 EFI mmap, 12 EFI64 system
table, 14/15 ACPI RSDP).

## Metadata
- **Complexity**: Medium
- **Source PRD**: `auton-windows-linux.prd.md`
- **PRD Phase**: B3
- **Estimated Files**: 7
- **Depends on**: `w12-kernel-base`; A1 per the PRD (the Linux runner validates the Linux toolchain path)

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | base `Makefile` | 10-60 | `iso` and `iso-neural` rules; `GRUB_MKRESCUE` |
| P0 | `agent/kernel_spec/templates/x86_64/{Makefile,grub/*}` | all | what the scaffold lays: change it here, not in trees |
| P0 | `agent/kernel_spec/subsystems/boot.md` | 20-160 | `boot_info_t`; which tags are parsed; "must also parse type 3" precedent |
| P0 | `scripts/lib/toolchain.sh` | 15-30 | per-platform GRUB tool names |
| P1 | `tests/kernel/identity_test.c` style | — | host-proving parsers |

## External Documentation
| Topic | Source | Key Takeaway |
|---|---|---|
| Multiboot2 under EFI | Multiboot2 spec §3.6.18 (EFI memory map, type 17), §3.6.13-14 (ACPI), §3.6.11 (EFI64 system table, type 12), §3.6.20 "boot services not terminated" | GRUB may still provide a BIOS-style type-6 mmap; do not assume it |
| grub-mkrescue | GRUB manual | a hybrid ISO needs both `i386-pc` and `x86_64-efi` module dirs installed |
| OVMF in QEMU | QEMU docs | `-drive if=pflash,format=raw,readonly=on,file=edk2-x86_64-code.fd` |

GOTCHA: Homebrew's `i686-elf-grub` ships only `i386-pc`. UEFI needs `x86_64-elf-grub`
(`brew install x86_64-elf-grub`) and the `--directory` of both targets, or two separate ISOs.
Linux: `grub-efi-amd64-bin`.
GOTCHA: under UEFI there is no VGA text buffer. Serial (`-serial stdio`) is the only console the
markers can rely on, so confirm the kernel never writes to 0xB8000 unconditionally.

## Patterns to Mirror
### TOOLCHAIN_ENV_WINS
// SOURCE: scripts/lib/toolchain.sh:18-30: `: "${GRUB_MKRESCUE:=…}"`.
### ACCEL_REFUSAL
// SOURCE: scripts/lib/toolchain.sh `auton_accel`: an explicit unmet request fails loudly. `--firmware uefi` without OVMF must do the same.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/kernel_spec/templates/x86_64/grub/grub-efi.cfg` | CREATE | `insmod efi_gop`, serial terminal, `multiboot2 /boot/kernel.bin` |
| `agent/kernel_spec/templates/x86_64/Makefile` | UPDATE | `iso-efi` / hybrid target; `GRUB_EFI_DIR` variable |
| `scripts/lib/toolchain.sh` | UPDATE | `GRUB_EFI_DIR` per platform; `auton_ovmf()` locating firmware (Homebrew share dir, `/usr/share/OVMF`), refusing if absent when asked for |
| `scripts/e2e.sh`, `scripts/auton-boot.sh` | UPDATE | `--firmware {bios,uefi}` |
| `agent/kernel_spec/subsystems/boot.md` | UPDATE | REQUIRED: parse type 17 when present, prefer it over type 6 under EFI; RSDP from 14/15 |
| `tests/kernel/boot_info_test.c` + `boot_info_reference` + runner | CREATE | synthetic tag streams (BIOS shape, EFI shape) through the parser |
| `docs/HOST-MATRIX.md` | UPDATE | the firmware column |

## NOT Building
- Secure Boot (an unsigned image; stated).
- A native EFI application (no GRUB).

## Step-by-Step Tasks
### Task 1: Parser test first (EFI-shaped tag stream)
### Task 2: Template + Makefile target (hybrid ISO)
- **VALIDATE**: `xorriso -indev auton.iso -report_el_torito plain` lists both a BIOS and an EFI boot entry.
### Task 3: `--firmware uefi` in the entry points with the OVMF probe
### Task 4: Boot to all markers under OVMF, both on Mac TCG and in CI
- **VALIDATE**: 12/12 markers with `--firmware uefi`, and still with `bios`.

## Validation Commands
```bash
tests/kernel/run_boot_info_test.sh --self-test
make -C <ws> iso-efi && scripts/e2e.sh --target <ws> --skip-train --firmware uefi
```

## Acceptance Criteria
- [ ] Boots to `auton>` under QEMU+OVMF with all markers
- [ ] BIOS boot unchanged
- [ ] EFI tags parsed, host-proved

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The kernel writes VGA text under EFI | M | M | the gotcha check; serial-only markers |
| The EFI memory map layout differs from the type-6 assumptions | M | H | the parser test with an EFI-shaped stream |
