#!/usr/bin/env bash
# Build the seed kernel ISO and boot it in QEMU with serial on stdio.
set -euo pipefail

# Usage: scripts/auton-boot.sh [--accel NAME] [ARCH]
ACCEL_REQ=""
case "${1:-}" in
	--accel)   ACCEL_REQ="${2:?--accel needs a value}"; shift 2 ;;
	--accel=*) ACCEL_REQ="${1#*=}"; shift ;;
esac
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
	echo "or restore the reference: git checkout kernel-reference-v1 -- kernels/" >&2
	exit 2
fi
cd "$KDIR"

make iso
exec "$QEMU" -accel "$AUTON_ACCEL" -cdrom build/auton.iso \
	-serial stdio -display none -no-reboot -m "${MEM:-128M}"
