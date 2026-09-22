#!/usr/bin/env bash
# Build a UEFI-bootable ISO from an ISO directory a kernel tree's `make` made.
#
#   scripts/iso-efi.sh <isodir> <out.iso>
#
# Packaging is the factory's job, not the kernel's, so trees keep their BIOS
# Makefile and this reuses what `make iso` / `make iso-neural` laid out (kernel,
# modules, grub.cfg). On Linux with grub-pc-bin and grub-efi-amd64-bin both
# installed, the result boots under BIOS too.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"
DIR="${1:?usage: iso-efi.sh <isodir> <out.iso>}"
OUT="${2:?usage: iso-efi.sh <isodir> <out.iso>}"
[ -f "$DIR/boot/kernel.bin" ] || { echo "no boot/kernel.bin in $DIR (run make iso first)" >&2; exit 2; }
command -v "$GRUB_MKRESCUE_EFI" >/dev/null || {
	echo "$GRUB_MKRESCUE_EFI not found: macOS: brew install x86_64-elf-grub;" >&2
	echo "Linux: apt install grub-efi-amd64-bin" >&2
	exit 2
}
"$GRUB_MKRESCUE_EFI" -o "$OUT" "$DIR" 2>/dev/null || { echo "grub-mkrescue (EFI) failed" >&2; exit 1; }
if ! xorriso -indev "$OUT" -report_el_torito plain 2>/dev/null | grep -q "UEFI"; then
	echo "$OUT has no UEFI El Torito entry: the EFI GRUB target is missing" >&2
	exit 1
fi
echo "built $OUT (UEFI)"
