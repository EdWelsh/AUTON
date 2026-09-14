#!/usr/bin/env bash
# Compile and run the silicon identity tests on the host.
#
#   tests/kernel/run_identity_test.sh --self-test     # against the reference
#   KERNEL_TREE=<dir> tests/kernel/run_identity_test.sh
#
# The folding formula is validated against documented parts on any host. The
# live CPUID cross-check runs only on x86 and announces itself skipped
# elsewhere, rather than passing silently.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/auton_identity_test"

if [ "${1:-}" = "--self-test" ]; then
	echo "self-test: reference implementation (tests/kernel/identity_reference/)"
	clang -O1 -g -fsanitize=address,undefined \
		-I"$HERE/identity_reference/include" \
		"$HERE/identity_test.c" "$HERE/identity_reference/identity.c" \
		-o "$OUT" || exit 1
	exec "$OUT"
fi

if [ ! -d "$KERNEL_TREE/kernel" ]; then
	echo "no kernel tree at $KERNEL_TREE — nothing to verify." >&2
	exit 2
fi
# exit 2 = not generated, exit 1 = generated wrong. An absent capture must not
# read as a broken one.
if [ ! -f "$KERNEL_TREE/kernel/include/identity.h" ]; then
	echo "no kernel/include/identity.h in $KERNEL_TREE." >&2
	echo "Silicon identity is specified in agent/kernel_spec/arch/hal.md" >&2
	echo "(category 8) but has not been generated into this tree. Run" >&2
	echo "--self-test to check the suite against the reference." >&2
	exit 2
fi

SOURCES=""
for c in kernel/arch/x86_64/cpu/identity.c kernel/dev/identity.c; do
	[ -f "$KERNEL_TREE/$c" ] && SOURCES="$SOURCES $KERNEL_TREE/$c"
done
[ -n "$SOURCES" ] || { echo "identity.h present but no identity.c behind it." >&2; exit 1; }

# shellcheck disable=SC2086
clang -O1 -g -fsanitize=address,undefined \
	-I"$KERNEL_TREE/kernel/include" \
	"$HERE/identity_test.c" $SOURCES -o "$OUT" || {
		echo "compile failed — the generated capture does not match hal.md category 8" >&2
		exit 1
	}
exec "$OUT"
