#!/usr/bin/env bash
# Compile and run the degenerate-output guard test on the host.
#
# The guard decides whether the OS speaks or falls back to the rule engine, so
# its logic is exercised directly rather than only when a model happens to
# misbehave — which is a test that never runs when things are healthy.
#
# Usage: tests/run_degenerate_test.sh
set -uo pipefail
cd "$(dirname "$0")/.."
clang -O1 -Ikernel/include \
	tests/degenerate_test.c kernel/slm/neural/neural_backend.c kernel/lib/kmath.c \
	-lm -o /tmp/auton_degenerate_test || exit 1
exec /tmp/auton_degenerate_test
