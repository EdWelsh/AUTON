#!/usr/bin/env bash
# Compile and run the allocator tests on the host against a generated tree.
#
# The kernel tree is a parameter, not a constant: kernels/ is generated output
# and there will be one tree per intent. Verification lives here so an agent
# that generates an allocator cannot also generate the test that approves it.
#
# Usage: KERNEL_TREE=kernels/x86_64 tests/kernel/run_mm_test.sh
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/auton_mm_test"

# --self-test builds against the reference implementation instead of a kernel
# tree. It proves the suite itself is right — these tests are the deliverable
# for an allocator that does not exist yet, and a test that has never been
# executed is an assertion.
if [ "${1:-}" = "--self-test" ]; then
	echo "self-test: reference implementation (tests/kernel/mm_reference/)"
	clang -O1 -g -fsanitize=address,undefined \
		-I"$HERE/mm_reference/include" \
		"$HERE/mm_test.c" "$HERE/mm_reference/pmm.c" -o "$OUT" || exit 1
	exec "$OUT"
fi

if [ ! -d "$KERNEL_TREE/kernel" ]; then
	echo "no kernel tree at $KERNEL_TREE — nothing to verify." >&2
	exit 2
fi

# `exit 2` means "not generated yet", `exit 1` means "generated wrong". Keeping
# those apart is what stops an absent allocator from reading as a failing one.
if [ ! -f "$KERNEL_TREE/kernel/include/mm.h" ]; then
	echo "no kernel/include/mm.h in $KERNEL_TREE." >&2
	echo "The allocator is specified in agent/kernel_spec/subsystems/mm.md but" >&2
	echo "has not been generated into this tree. Run --self-test to check the" >&2
	echo "suite itself against the reference implementation." >&2
	exit 2
fi

SOURCES=""
for candidate in kernel/mm/pmm.c kernel/mm/slab.c kernel/mm/vmm.c kernel/lib/phys.c; do
	[ -f "$KERNEL_TREE/$candidate" ] && SOURCES="$SOURCES $KERNEL_TREE/$candidate"
done
if [ -z "$SOURCES" ]; then
	echo "mm.h is present but no allocator sources are (looked for kernel/mm/*.c," >&2
	echo "kernel/lib/phys.c) — the interface exists with nothing behind it." >&2
	exit 1
fi

# shellcheck disable=SC2086
clang -O1 -g -fsanitize=address,undefined \
	-I"$KERNEL_TREE/kernel/include" \
	"$HERE/mm_test.c" $SOURCES \
	-o "$OUT" || {
		echo "compile failed — the generated allocator does not match mm.md's interface" >&2
		exit 1
	}
exec "$OUT"
