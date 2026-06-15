#!/usr/bin/env bash
# Build the seed kernel ISO, boot it, and verify the acceptance serial markers
# (the strings kernel_spec/tests/acceptance_tests.py greps for).
set -uo pipefail

ARCH="${1:-x86_64}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/kernels/$ARCH"

make CC="${CC:-gcc}" iso >/dev/null 2>&1 || { echo "build failed"; exit 1; }

OUT="$(timeout "${BOOT_TIMEOUT:-45}" qemu-system-x86_64 -cdrom build/auton.iso \
	-serial stdio -display none -no-reboot -m "${MEM:-128M}" 2>/dev/null || true)"

echo "----- serial output -----"
echo "$OUT"
echo "-------------------------"

fail=0
check() {
	if echo "$OUT" | grep -qE "$1"; then
		echo "PASS  $1"
	else
		echo "FAIL  $1"
		fail=1
	fi
}

check "AUTON Kernel booting"
check "\[BOOT\] Multiboot2 magic valid"
check "\[BOOT\] Long mode enabled"
check "\[BOOT\] 64-bit GDT loaded"
check "\[BOOT\] Interrupts initialized"
check "\[DRV\] Serial .+ initialized"
check "\[MM\] PMM initialized"
check "\[SCHED\] Scheduler initialized"
check "\[DEV\] PCI scan: [0-9]+ devices found"
check "\[SLM\] Rule engine initialized"
check "\[SLM\] Ready"
check "\[BOOT\] OK"

if [ "$fail" -eq 0 ]; then
	echo "ALL PASS"
else
	echo "FAILURES"
	exit 1
fi
