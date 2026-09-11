#!/usr/bin/env bash
# Build the seed kernel ISO and boot it in QEMU with serial on stdio.
set -euo pipefail

ARCH="${1:-x86_64}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"
cd "$ROOT/kernels/$ARCH"

make iso
exec "$QEMU" -cdrom build/auton.iso \
	-serial stdio -display none -no-reboot -m "${MEM:-128M}"
