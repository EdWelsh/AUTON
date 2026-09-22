#!/usr/bin/env bash
# Build the seed kernel ISO and boot it in QEMU with serial on stdio.
set -euo pipefail

# Usage: scripts/auton-boot.sh [--accel NAME] [--firmware bios|uefi] [ARCH]
ACCEL_REQ="" FIRMWARE="bios"
while [ $# -gt 0 ]; do
	case "$1" in
		--accel)      ACCEL_REQ="${2:?--accel needs a value}"; shift 2 ;;
		--accel=*)    ACCEL_REQ="${1#*=}"; shift ;;
		--firmware)   FIRMWARE="${2:?--firmware needs bios or uefi}"; shift 2 ;;
		--firmware=*) FIRMWARE="${1#*=}"; shift ;;
		*) break ;;
	esac
done
ARCH="${1:-x86_64}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"
auton_accel "$ACCEL_REQ" || exit 2
KDIR="$ROOT/kernels/$ARCH"
# The kernel tree is agent-generated output and may not exist. Say so plainly:
# "build failed" implies a broken build, not an absent one.
if [ ! -d "$KDIR/kernel" ]; then
	echo "no kernel tree at ${KDIR#"$ROOT"/}" >&2
	echo "AUTON's premise is that the agents write it (README.md). Generate one," >&2
	echo "or extract the agreed base: scripts/kernel-base.sh kernels/x86_64" >&2
	exit 2
fi
cd "$KDIR"

make iso
ISO=build/auton.iso FW=()
case "$FIRMWARE" in
	bios) ;;
	uefi)
		auton_ovmf || exit 2
		"$ROOT/scripts/iso-efi.sh" build/isodir build/auton-efi.iso || exit 1
		ISO=build/auton-efi.iso
		FW=(-machine pc -drive "if=pflash,format=raw,readonly=on,file=$AUTON_OVMF_CODE") ;;
	*) echo "unknown firmware: $FIRMWARE (expected bios or uefi)" >&2; exit 2 ;;
esac
exec "$QEMU" -accel "$AUTON_ACCEL" ${FW[@]+"${FW[@]}"} -cdrom "$ISO" \
	-serial stdio -display none -no-reboot -m "${MEM:-128M}"
