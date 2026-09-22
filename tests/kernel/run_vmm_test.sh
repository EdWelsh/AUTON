#!/usr/bin/env bash
# Compile and run the VMM tests on the host, against the reference or a tree.
#
#   tests/kernel/run_vmm_test.sh --self-test          # against vmm_reference/
#   KERNEL_TREE=<dir> tests/kernel/run_vmm_test.sh    # against a generated VMM
#
# Verification lives here, outside the tree it verifies, so an agent that
# generates a VMM cannot also generate the test that approves it.
# exit 2 = not generated, exit 1 = generated wrong (as run_mm_test.sh).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/auton_vmm_test"
CC="${HOST_CC:-clang}"
FLAGS=(-O1 -g -fsanitize=address,undefined -fno-sanitize-recover=undefined)

if [ "${1:-}" = "--self-test" ]; then
	echo "self-test: reference implementation (tests/kernel/vmm_reference/)"
	"$CC" "${FLAGS[@]}" -I"$HERE/vmm_reference/include" \
		"$HERE/vmm_test.c" "$HERE/vmm_reference/vmm.c" -o "$OUT" || exit 1
	exec "$OUT"
fi

KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
if [ ! -f "$KERNEL_TREE/kernel/mm/vmm.c" ]; then
	echo "no kernel/mm/vmm.c in $KERNEL_TREE." >&2
	echo "The VMM is specified in agent/kernel_spec/subsystems/mm.md and has not" >&2
	echo "been generated into this tree. Run --self-test to check the suite." >&2
	exit 2
fi
# The tree's mm.h must declare the interface; the host hooks come from the
# test's own vmm_host.h, which is exactly what the kernel's PMM and HAL provide.
"$CC" "${FLAGS[@]}" -DAUTON_HOST_TEST \
	-I"$KERNEL_TREE/kernel/include" -I"$HERE/vmm_reference/include" \
	"$HERE/vmm_test.c" "$KERNEL_TREE/kernel/mm/vmm.c" -o "$OUT" || {
		echo "compile failed: the generated VMM does not match mm.md's interface" >&2
		exit 1
	}
exec "$OUT"
