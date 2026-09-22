#!/usr/bin/env bash
# Host suite for the KV store (agent/kernel_spec/services/kvstore.md).
#
#   tests/kernel/run_kvstore_test.sh --self-test
#   KERNEL_TREE=<dir> tests/kernel/run_kvstore_test.sh
#
# Proves the RESP2 parser, the command semantics, the limits and the log's
# replay. It proves nothing about persistence across a real reboot: that is
# scripts/run-storage-acceptance.sh --service kvstore, with redis-cli.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/auton_kvstore_test"
CC="${CC_HOST:-clang}"
command -v "$CC" >/dev/null 2>&1 || CC=cc

if [ "${1:-}" = "--self-test" ]; then
	echo "self-test: reference implementation (tests/kernel/kvstore_reference/)"
	SOURCES=("$HERE/kvstore_reference/kvstore.c")
	INC=(-I"$HERE/kvstore_reference/include")
else
	KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
	case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
	if [ ! -d "$KERNEL_TREE/kernel" ]; then
		echo "no kernel tree at $KERNEL_TREE — nothing to verify." >&2
		exit 2
	fi
	SOURCES=()
	for c in kernel/services/kvstore/kvstore.c kernel/services/kvstore/kv.c; do
		[ -f "$KERNEL_TREE/$c" ] && SOURCES+=("$KERNEL_TREE/$c")
	done
	if [ "${#SOURCES[@]}" -eq 0 ]; then
		echo "not generated: no kernel/services/kvstore/kvstore.c in $KERNEL_TREE." >&2
		echo "kvstore is specified in agent/kernel_spec/services/kvstore.md." >&2
		exit 2
	fi
	INC=(-I"$KERNEL_TREE/kernel/include" -I"$HERE/kvstore_reference/include")
fi

"$CC" -O1 -g -fsanitize=address,undefined "${INC[@]}" \
	"$HERE/kvstore_test.c" "${SOURCES[@]}" -o "$OUT" || {
		echo "compile failed — the implementation does not match kvstore.md's interface" >&2
		exit 1
	}
exec "$OUT"
