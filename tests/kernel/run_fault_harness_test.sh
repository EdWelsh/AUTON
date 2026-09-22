#!/usr/bin/env bash
# The in-kernel fault harness's state machine (x86_64.md, "Expected Faults").
#
#   tests/kernel/run_fault_harness_test.sh --self-test
#   KERNEL_TREE=<dir> tests/kernel/run_fault_harness_test.sh
#
# A tree without arch_expect_fault cannot run the in-kernel conformance suite,
# and this exits 2 to say so. A suite that did not run has found nothing, and
# must never be counted as a clean result.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/auton_fault_harness_test"
CC="${CC_HOST:-clang}"
command -v "$CC" >/dev/null 2>&1 || CC=cc

if [ "${1:-}" = "--self-test" ]; then
	echo "self-test: reference implementation (tests/kernel/fault_harness_reference/)"
	SOURCES=("$HERE/fault_harness_reference/fault_harness.c")
	INC=(-I"$HERE/fault_harness_reference/include")
else
	KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
	case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
	if [ ! -d "$KERNEL_TREE/kernel" ]; then
		echo "no kernel tree at $KERNEL_TREE — nothing to verify." >&2
		exit 2
	fi
	SOURCES=()
	for c in kernel/arch/x86_64/fault_harness.c kernel/arch/x86_64/expect_fault.c; do
		[ -f "$KERNEL_TREE/$c" ] && SOURCES+=("$KERNEL_TREE/$c")
	done
	if [ "${#SOURCES[@]}" -eq 0 ]; then
		echo "not generated: no arch_expect_fault in $KERNEL_TREE." >&2
		echo "x86_64.md 'Expected Faults' specifies it; without it the in-kernel" >&2
		echo "conformance suite cannot run, and zero divergences would be a lie." >&2
		exit 2
	fi
	INC=(-I"$KERNEL_TREE/kernel/include" -I"$HERE/fault_harness_reference/include")
fi

"$CC" -O1 -g -fsanitize=address,undefined "${INC[@]}" \
	"$HERE/fault_harness_test.c" "${SOURCES[@]}" -o "$OUT" || {
		echo "compile failed — the implementation does not match x86_64.md" >&2
		exit 1
	}
exec "$OUT"
