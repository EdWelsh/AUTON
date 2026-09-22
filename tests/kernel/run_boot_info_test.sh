#!/usr/bin/env bash
# Multiboot2 boot-info parsing, BIOS and UEFI tag shapes, on the host.
#   tests/kernel/run_boot_info_test.sh --self-test        # against boot_info_reference/
#   KERNEL_TREE=<dir> tests/kernel/run_boot_info_test.sh  # against a tree's boot_info.c
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/auton_boot_info_test"
CC="${HOST_CC:-clang}"
FLAGS=(-O1 -g -fsanitize=address,undefined -fno-sanitize-recover=undefined)
if [ "${1:-}" = "--self-test" ]; then
	echo "self-test: reference (tests/kernel/boot_info_reference/)"
	INC="$HERE/boot_info_reference/include"; SRC="$HERE/boot_info_reference/boot_info.c"
else
	KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
	case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
	SRC="$KERNEL_TREE/kernel/boot/boot_info.c"; INC="$KERNEL_TREE/kernel/include"
	[ -f "$SRC" ] || { echo "no kernel/boot/boot_info.c in $KERNEL_TREE" >&2; exit 2; }
fi
"$CC" "${FLAGS[@]}" -I"$INC" "$HERE/boot_info_test.c" "$SRC" -o "$OUT" || {
	echo "compile failed: boot_info does not match boot.md's interface" >&2; exit 1; }
exec "$OUT"
