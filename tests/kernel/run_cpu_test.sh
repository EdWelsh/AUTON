#!/usr/bin/env bash
# Compile and run the cpu-feature tests on the host against a generated tree.
#
#   tests/kernel/run_cpu_test.sh --self-test   # the suite against its reference
#   tests/kernel/run_cpu_test.sh --inject      # each injected defect must fail the suite
#   KERNEL_TREE=<dir> tests/kernel/run_cpu_test.sh
#
# Exit 0 pass, 1 generated wrong, 2 not generated. The CPU is faked through the
# cpu_raw_* seam (cpu_reference/include/cpu.h), so this runs on any host.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KERNEL_TREE="${KERNEL_TREE:-$ROOT/.artifacts/kernels/x86_64}"
case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/auton_cpu_test"
CC_FLAGS=(-O1 -g -fsanitize=address,undefined -Wall)

if [ "${1:-}" = "--self-test" ]; then
	echo "self-test: reference implementation (tests/kernel/cpu_reference/)"
	clang "${CC_FLAGS[@]}" -I"$HERE/cpu_reference/include" \
		"$HERE/cpu_test.c" "$HERE/cpu_reference/cpu.c" -o "$OUT" || exit 1
	exec "$OUT"
fi

if [ "${1:-}" = "--inject" ]; then
	BUGS=13
	caught=0
	for n in $(seq 1 "$BUGS"); do
		clang "${CC_FLAGS[@]}" -DBUG_$n -I"$HERE/cpu_reference/include" \
			"$HERE/cpu_test.c" "$HERE/cpu_reference/cpu.c" -o "$OUT.bug$n" 2>/dev/null \
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
if [ ! -f "$KERNEL_TREE/kernel/include/cpu.h" ]; then
	echo "no kernel/include/cpu.h in $KERNEL_TREE: the cpu subsystem is not generated" >&2
	echo "(agent/kernel_spec/subsystems/cpu.md). --self-test checks the suite itself." >&2
	exit 2
fi
SOURCES=""
for c in kernel/cpu/cpu.c kernel/arch/x86_64/cpu/cpu.c kernel/lib/cpu.c; do
	[ -f "$KERNEL_TREE/$c" ] && SOURCES="$SOURCES $KERNEL_TREE/$c"
done
if [ -z "$SOURCES" ]; then
	echo "cpu.h is present but no cpu.c is (looked for kernel/cpu/cpu.c," >&2
	echo "kernel/arch/x86_64/cpu/cpu.c, kernel/lib/cpu.c): not generated." >&2
	exit 2
fi
# shellcheck disable=SC2086
clang "${CC_FLAGS[@]}" -I"$KERNEL_TREE/kernel/include" \
	"$HERE/cpu_test.c" $SOURCES -o "$OUT" || {
		echo "compile failed — the generated subsystem does not match the interface in cpu.md" >&2
		exit 1
	}
exec "$OUT"
