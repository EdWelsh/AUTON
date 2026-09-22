#!/usr/bin/env bash
# Host suite for the SMTP service (agent/kernel_spec/services/smtp.md).
#
#   tests/kernel/run_smtp_test.sh --self-test
#   KERNEL_TREE=<dir> tests/kernel/run_smtp_test.sh
#
# The state machine, the limits, relay refusal, dot-stuffing and sequence
# recovery. That a real client delivers mail which survives a reboot is the
# acceptance step: scripts/run-storage-acceptance.sh --service smtp, driven by
# Python's smtplib.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/auton_smtp_test"
CC="${CC_HOST:-clang}"
command -v "$CC" >/dev/null 2>&1 || CC=cc

if [ "${1:-}" = "--self-test" ]; then
	echo "self-test: reference implementation (tests/kernel/smtp_reference/)"
	SOURCES=("$HERE/smtp_reference/smtp.c")
	INC=(-I"$HERE/smtp_reference/include")
else
	KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
	case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
	if [ ! -d "$KERNEL_TREE/kernel" ]; then
		echo "no kernel tree at $KERNEL_TREE — nothing to verify." >&2
		exit 2
	fi
	SOURCES=()
	for c in kernel/services/smtp/smtp.c kernel/services/smtp/server.c; do
		[ -f "$KERNEL_TREE/$c" ] && SOURCES+=("$KERNEL_TREE/$c")
	done
	if [ "${#SOURCES[@]}" -eq 0 ]; then
		echo "not generated: no kernel/services/smtp/smtp.c in $KERNEL_TREE." >&2
		exit 2
	fi
	INC=(-I"$KERNEL_TREE/kernel/include" -I"$HERE/smtp_reference/include")
fi

"$CC" -O1 -g -fsanitize=address,undefined "${INC[@]}" \
	"$HERE/smtp_test.c" "${SOURCES[@]}" -o "$OUT" || {
		echo "compile failed — the implementation does not match smtp.md" >&2
		exit 1
	}
exec "$OUT"
