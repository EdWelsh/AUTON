#!/usr/bin/env bash
# Build the seed kernel ISO and boot it in QEMU on THIS host — no Docker.
# The Docker path (scripts/auton-boot.sh, docker compose run os) still works and
# remains the fallback; this is the fast local loop.
#
#   scripts/auton-boot-native.sh                      # rule-engine kernel, 128M
#   MEM=512M scripts/auton-boot-native.sh             # more RAM
#   MODEL=$PWD/SLM/work/auton-slm.bin scripts/auton-boot-native.sh   # neural, 256M
set -euo pipefail

ARCH="${1:-x86_64}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"

# Fail early and loudly on a missing tool or a full disk; stay quiet when fine.
if ! preflight_out="$("$ROOT/scripts/preflight.sh" 2>&1)"; then
	echo "$preflight_out"
	exit 1
fi

cd "$ROOT/kernels/$ARCH"

if [ -n "${MODEL:-}" ]; then
	# Boot the on-device model as a Multiboot2 module. Needs >=128 MB for the
	# neural backend to be selected (see slm_init), so default higher.
	make iso-neural MODEL="$MODEL"
	exec "$QEMU" -cdrom build/auton-neural.iso \
		-serial stdio -display none -no-reboot -m "${MEM:-256M}"
fi

make iso
exec "$QEMU" -cdrom build/auton.iso \
	-serial stdio -display none -no-reboot -m "${MEM:-128M}"
