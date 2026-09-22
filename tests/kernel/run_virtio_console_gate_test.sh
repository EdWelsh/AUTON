#!/usr/bin/env bash
# The V8 gate suite (VirtIO Console), frozen before the agent's run.
#
#   tests/kernel/run_virtio_console_gate_test.sh --self-test   # the human reference
#   KERNEL_TREE=<dir> tests/kernel/run_virtio_console_gate_test.sh
#
# Tree mode judges the agent's reference at <tree>/tests/kernel/virtio_console_reference.c
# (the path agent/tools/authorship.yaml measures), against the frozen interface
# in virtio_console_gate/include/. Exit 2 not generated, exit 1 wrong.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/auton_virtio_console_gate"
CC="${CC_HOST:-clang}"
command -v "$CC" >/dev/null 2>&1 || CC=cc
INC=(-I"$HERE/virtio_console_gate/include" -I"$HERE/virtio_reference/include")

if [ "${1:-}" = "--self-test" ]; then
	echo "self-test: human reference (tests/kernel/virtio_console_gate/reference.c)"
	SUBJECT="$HERE/virtio_console_gate/reference.c"
else
	TREE="${KERNEL_TREE:-}"
	[ -n "$TREE" ] && [ -d "$TREE" ] || { echo "set KERNEL_TREE, or pass --self-test" >&2; exit 2; }
	SUBJECT="$TREE/tests/kernel/virtio_console_reference.c"
	[ -f "$SUBJECT" ] || { echo "not generated: no tests/kernel/virtio_console_reference.c in $TREE" >&2; exit 2; }
fi

"$CC" -O1 -g -fsanitize=address,undefined "${INC[@]}" \
	"$HERE/virtio_console_gate_test.c" "$SUBJECT" "$HERE/virtio_reference/virtio_ref.c" \
	-o "$OUT" || { echo "compile failed: the reference does not match the frozen interface" >&2; exit 1; }
exec "$OUT"
