#!/usr/bin/env bash
# Prove the aarch64 scaffolding before anything is generated onto it.
#
#   tests/kernel/run_aarch64_smoke.sh
#
# Builds the smallest image that can speak (boot.S + main.c) with the SAME
# linker script and flags the scaffold places, and boots it on QEMU's virt.
# What this proves: the linker script's base address, that -kernel loads the
# ELF, that X0 holds a device tree, and that the PL011 is where the dumped
# tree says. A later generation failure is then in the generated code.
#
# Exit 0 pass, 1 wrong, 2 the toolchain or QEMU is missing (says which).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
export ARCH=aarch64
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"

command -v "$CC" >/dev/null || {
	echo "no $CC: brew install aarch64-elf-gcc (Darwin), apt install gcc-aarch64-linux-gnu" >&2
	exit 2; }
command -v "$QEMU" >/dev/null || { echo "no $QEMU: brew install qemu" >&2; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
LD="$ROOT/agent/kernel_spec/templates/aarch64/arch/linker.ld"

"$CC" -ffreestanding -fno-stack-protector -fno-pic -fno-pie \
	-mgeneral-regs-only -mstrict-align -std=gnu11 -O2 -Wall -Wextra \
	-nostdlib -no-pie -Wl,--build-id=none -Wl,--no-warn-rwx-segments -Wl,-T,"$LD" \
	"$HERE/aarch64_smoke/boot.S" "$HERE/aarch64_smoke/main.c" \
	-o "$WORK/smoke.elf" 2>"$WORK/build.log" || {
		echo "build failed:"; sed 's/^/  /' "$WORK/build.log" | head -10; exit 1; }

# A FLAT image, because QEMU only follows the Linux arm64 boot protocol — the
# one that puts the DTB in X0 — for a raw image. The same kernel booted as an
# ELF starts with X0 = 0, which is why "dtb in x0" below is a real check and
# not a formality.
OBJCOPY="${OBJCOPY:-$(echo "$CC" | sed 's/-gcc$/-objcopy/')}"
command -v "$OBJCOPY" >/dev/null || { echo "no $OBJCOPY" >&2; exit 2; }
"$OBJCOPY" -O binary "$WORK/smoke.elf" "$WORK/smoke.bin" || exit 1

SERIAL="$WORK/serial.log"
auton_timeout "${BOOT_TIMEOUT:-30}" "$QEMU" -M virt,gic-version=2 -cpu cortex-a72 \
	-m 256M -kernel "$WORK/smoke.bin" -serial "file:$SERIAL" -display none \
	-no-reboot </dev/null >/dev/null 2>&1 || true

echo "----- serial -----"
cat "$SERIAL" 2>/dev/null
echo "------------------"

fail=0
for marker in "[BOOT] aarch64 smoke" "[BOOT] dtb in x0" "[BOOT] OK"; do
	if grep -qaF "$marker" "$SERIAL" 2>/dev/null; then
		echo "PASS  $marker"
	else
		echo "FAIL  $marker"
		fail=1
	fi
done
[ "$fail" -eq 0 ] && echo "aarch64 scaffolding: PASS"
exit "$fail"
