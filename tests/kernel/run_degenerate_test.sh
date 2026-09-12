#!/usr/bin/env bash
# Compile and run the degenerate-output guard test on the host.
#
# The guard decides whether the OS speaks or falls back to the rule engine, so
# its logic is exercised directly rather than only when a model happens to
# misbehave — which is a test that never runs when things are healthy.
#
# Usage: tests/run_degenerate_test.sh
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Kernel tree is a parameter; see neural_parity.sh for why.
KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac

if [ ! -d "$KERNEL_TREE/kernel" ]; then
	echo "no kernel tree at $KERNEL_TREE — nothing to verify." >&2
	exit 2
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$KERNEL_TREE"
clang -O1 -Ikernel/include \
	"$HERE/degenerate_test.c" kernel/slm/neural/neural_backend.c kernel/lib/kmath.c \
	-lm -o /tmp/auton_degenerate_test || exit 1
exec /tmp/auton_degenerate_test
