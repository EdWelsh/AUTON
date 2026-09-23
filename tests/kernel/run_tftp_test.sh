#!/usr/bin/env bash
# The TFTP gate suite (services/tftp.md), frozen before the F6 re-run.
#   tests/kernel/run_tftp_test.sh --self-test          # against tftp_reference/
#   KERNEL_TREE=<dir> tests/kernel/run_tftp_test.sh    # against a generated server
# exit 2 = not generated, exit 1 = generated wrong.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/auton_tftp_test"
CC="${HOST_CC:-clang}"
FLAGS=(-O1 -g -fsanitize=address,undefined -fno-sanitize-recover=undefined)
if [ "${1:-}" = "--self-test" ]; then
	echo "self-test: reference (tests/kernel/tftp_reference/)"
	INC="$HERE/tftp_reference/include"; SRC="$HERE/tftp_reference/server.c"
else
	KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
	case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
	SRC="$KERNEL_TREE/kernel/services/tftp/server.c"; INC="$KERNEL_TREE/kernel/include"
	[ -f "$SRC" ] || { echo "no TFTP server at $SRC: specified in services/tftp.md, not generated here." >&2; exit 2; }
fi
# The stubs stand in for the kernel's net.h and kernel.h (kprintf is captured);
# tftp.h is the tree's own.
"$CC" "${FLAGS[@]}" -I"$HERE/tftp_stub/include" -I"$INC" "$HERE/tftp_test.c" \
	"$HERE/tftp_stub/libk.c" "$SRC" -o "$OUT" || {
	echo "compile failed: the server does not match tftp.md's interface" >&2; exit 1; }
exec "$OUT"
