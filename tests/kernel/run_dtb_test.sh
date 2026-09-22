#!/usr/bin/env bash
# The aarch64 device-tree parser (agent/kernel_spec/arch/aarch64.md).
#
#   tests/kernel/run_dtb_test.sh --self-test
#   KERNEL_TREE=<dir> tests/kernel/run_dtb_test.sh
#
# The fixtures are real QEMU virt trees (dtb_fixtures/). This runs on any host:
# parsing a blob needs no aarch64, which is the point of having the parser be
# the first thing written for a new architecture.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/auton_dtb_test"
CC="${CC_HOST:-clang}"
command -v "$CC" >/dev/null 2>&1 || CC=cc

if [ "${1:-}" = "--self-test" ]; then
	echo "self-test: reference implementation (tests/kernel/dtb_reference/)"
	SOURCES=("$HERE/dtb_reference/fdt.c")
	INC=(-I"$HERE/dtb_reference/include")
else
	KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/aarch64}"
	case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
	if [ ! -d "$KERNEL_TREE/kernel" ]; then
		echo "no kernel tree at $KERNEL_TREE — nothing to verify." >&2
		exit 2
	fi
	SOURCES=()
	for c in kernel/arch/aarch64/dev/fdt.c kernel/arch/aarch64/fdt.c; do
		[ -f "$KERNEL_TREE/$c" ] && SOURCES+=("$KERNEL_TREE/$c")
	done
	if [ "${#SOURCES[@]}" -eq 0 ]; then
		echo "not generated: no kernel/arch/aarch64/dev/fdt.c in $KERNEL_TREE." >&2
		echo "aarch64.md specifies it; without a DTB parser the kernel cannot" >&2
		echo "find its own RAM or its UART." >&2
		exit 2
	fi
	INC=(-I"$KERNEL_TREE/kernel/include" -I"$HERE/dtb_reference/include")
fi

"$CC" -O1 -g -fsanitize=address,undefined "${INC[@]}" \
	"$HERE/dtb_test.c" "${SOURCES[@]}" -o "$OUT" || {
		echo "compile failed — the parser does not match aarch64.md's interface" >&2
		exit 1
	}
exec "$OUT" "$HERE/dtb_fixtures"
