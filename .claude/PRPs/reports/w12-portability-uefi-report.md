# Implementation Report: UEFI Boot Path under OVMF (B3)

**Plan**: `plans/completed/w12-portability-uefi.plan.md`

## Summary

AUTON boots under UEFI (QEMU + OVMF) to `auton>` with every marker the BIOS path prints, and the
UEFI e2e spine matches `docs/E2E-EXPECTED.yaml` exactly, as BIOS does. The first UEFI boot also
exposed a latent bug the plan predicted: **the base reported 7 MB RAM on a 256 MiB guest.**

## The finding

`boot_info.c` sized RAM from Multiboot2 tag 4 (basic memory). Its `mem_upper` counts only
contiguous RAM above 1 MiB up to the first hole. Under BIOS that is all of RAM; under OVMF the first
hole is near 8 MiB. `boot.md` already required the memory map, and BIOS hid the gap.
**`kernel-base-v4`** sums available tag-6 regions, else usable EFI types in tag 17 (by
`descr_size`, which firmware makes larger than the 40-byte descriptor), else tag 4. Result:
BIOS 255 MB, UEFI 249 MB.

## Tasks

| # | Task | Result |
|---|---|---|
| 1 | Parser test first | `tests/kernel/boot_info_test.c`, 9 checks, BIOS and UEFI shapes, via the new `boot_parse_info()`; the v3 parser fails it |
| 2 | Template + Makefile | **deviation**: no tree change. `scripts/iso-efi.sh` repacks the ISO directory `make` already produced; packaging belongs to the factory |
| 3 | `--firmware uefi` | e2e.sh (all three boots) and auton-boot.sh; `auton_ovmf` locates firmware and refuses loudly |
| 4 | Boot to all markers under OVMF | this Mac: spine matches the expectation under both firmwares; CI wired |

## Deviations

- **UEFI-only ISO on macOS.** Homebrew ships the BIOS and EFI GRUB targets as separate formulas,
  and `grub-mkrescue -d` takes one platform directory. A hybrid would mean writing into the
  Homebrew Cellar. On Linux, one `grub-mkrescue` builds a hybrid.
- **`-machine pc` under OVMF**, not q35: q35 presents an e1000e, so the NIC would differ between
  firmwares and the comparison would stop being like-for-like.
- **The base moved to v4** (the HAL plan's tag becomes v5).
