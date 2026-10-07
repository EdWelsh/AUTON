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
		"$HERE/mm_test.c" "$HERE/mm_host_env.c" "$HERE/mm_reference/pmm.c" -o "$OUT" || exit 1
	exec "$OUT"
fi

# --inject scores the suite: each BUG_n in the reference is one defect a plausible
# allocator ships with, and the suite must fail on every one. A suite that cannot
# fail is not evidence (w23 G1: it once missed an absorbed double free and an
# off-by-one at the end of RAM, and nobody could tell until a run was scored).
if [ "${1:-}" = "--inject" ]; then
	BUGS=9
	caught=0
	for n in $(seq 1 "$BUGS"); do
		clang -O1 -g -fsanitize=address,undefined -DBUG_$n \
			-I"$HERE/mm_reference/include" \
			"$HERE/mm_test.c" "$HERE/mm_host_env.c" "$HERE/mm_reference/pmm.c" \
			-o "$OUT.bug$n" 2>/dev/null \
			|| { echo "BUG_$n: did not compile — a broken bug is not a caught one"; continue; }
		if "$OUT.bug$n" >/dev/null 2>&1; then
			echo "BUG_$n: MISSED"
		else
			echo "BUG_$n: caught"
			caught=$((caught + 1))
		fi
		rm -f "$OUT.bug$n"
	done
	echo "injected-bug score: $caught/$BUGS"
	[ "$caught" -eq "$BUGS" ]
	exit $?
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

# The base ships kernel/lib/phys.c, so "some source exists" is always true;
# the allocator itself is kernel/mm/pmm.c, and without it nothing was generated.
if [ ! -f "$KERNEL_TREE/kernel/mm/pmm.c" ]; then
	echo "mm.h is present but kernel/mm/pmm.c is not: the allocator was not generated." >&2
	exit 2
fi
# boot.h belongs to the *boot* subsystem, which mm.md lists as a dependency
# ("boot: provides boot_mmap_t") and which an mm goal does not produce. Demanding
# it from the tree made this gate unpassable for the thing it gates: a correct
# allocator scored "generated wrong" because a different subsystem was absent.
#
# That is the tftp_stub defect again — a gate requiring an artifact from outside
# the scope of what it verifies — and it cost a five-hour run a real verdict. So
# the spec-derived reference header stands in when the tree has none. The tree's
# own boot.h still wins when it exists, because -I order puts the tree first.
BOOT_INCLUDE=""
if [ ! -f "$KERNEL_TREE/kernel/include/boot.h" ]; then
	BOOT_INCLUDE="-I$HERE/mm_reference/include"
	echo "note: kernel/include/boot.h absent; using boot.md's reference header" >&2
	echo "      from tests/kernel/mm_reference/include/. boot is a separate" >&2
	echo "      subsystem, so its absence is not an allocator defect." >&2
fi

SOURCES=""
# vmm.c is not linked here: it has its own suite (run_vmm_test.sh), which
# supplies the HAL hooks it calls; this suite does not, so including it made
# any tree with a VMM fail to link (w18 R1).
for candidate in kernel/mm/pmm.c kernel/mm/slab.c kernel/lib/phys.c; do
	[ -f "$KERNEL_TREE/$candidate" ] && SOURCES="$SOURCES $KERNEL_TREE/$candidate"
done
# The seed's phys.c is the bump allocator a PMM replaces. A tree whose PMM
# defines dma_alloc retires it from its build (it stays on disk, unmodified);
# linking it here anyway is a duplicate symbol the kernel never has (w18 R1).
# A definition line ends without ';' — a prototype does not.
if grep -qsE '^[A-Za-z_][A-Za-z_0-9 *]*[ *]dma_alloc[[:space:]]*\([^;]*$' \
		"$KERNEL_TREE"/kernel/mm/*.c; then
	SOURCES="${SOURCES/ $KERNEL_TREE\/kernel\/lib\/phys.c/}"
	echo "note: the tree's PMM defines dma_alloc; kernel/lib/phys.c is retired, not linked" >&2
fi
if [ -z "$SOURCES" ]; then
	echo "mm.h is present but no allocator sources are (looked for kernel/mm/*.c," >&2
	echo "kernel/lib/phys.c) — the interface exists with nothing behind it." >&2
	exit 1
fi

# shellcheck disable=SC2086
clang -O1 -g -fsanitize=address,undefined \
	-I"$KERNEL_TREE/kernel/include" $BOOT_INCLUDE \
	"$HERE/mm_test.c" "$HERE/mm_host_env.c" $SOURCES \
	-o "$OUT" || {
		echo "compile failed — the generated allocator does not match mm.md's interface" >&2
		exit 1
	}
exec "$OUT"
