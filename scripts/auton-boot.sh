#!/usr/bin/env bash
# Build the seed kernel ISO and boot it in QEMU with serial on stdio.
set -euo pipefail

ARCH="${1:-x86_64}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/kernels/$ARCH"

make CC="${CC:-gcc}" iso
exec qemu-system-x86_64 -cdrom build/auton.iso \
	-serial stdio -display none -no-reboot -m "${MEM:-128M}"
