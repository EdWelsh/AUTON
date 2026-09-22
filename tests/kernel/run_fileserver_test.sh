#!/usr/bin/env bash
# Host suite for the file server (agent/kernel_spec/services/fileserver.md).
#
#   tests/kernel/run_fileserver_test.sh --self-test
#   KERNEL_TREE=<dir> tests/kernel/run_fileserver_test.sh
#
# Path resolution and request parsing, which are what a host can prove. That
# curl retrieves a file written to the DISK is the acceptance step:
# scripts/run-storage-acceptance.sh --service fileserver.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/auton_fileserver_test"
CC="${CC_HOST:-clang}"
command -v "$CC" >/dev/null 2>&1 || CC=cc

if [ "${1:-}" = "--self-test" ]; then
	echo "self-test: reference implementation (tests/kernel/fileserver_reference/)"
	SOURCES=("$HERE/fileserver_reference/fileserver.c")
	INC=(-I"$HERE/fileserver_reference/include")
else
	KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
	case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
	if [ ! -d "$KERNEL_TREE/kernel" ]; then
		echo "no kernel tree at $KERNEL_TREE — nothing to verify." >&2
		exit 2
	fi
	SOURCES=()
	for c in kernel/services/fileserver/fileserver.c kernel/services/fileserver/http.c; do
		[ -f "$KERNEL_TREE/$c" ] && SOURCES+=("$KERNEL_TREE/$c")
	done
	if [ "${#SOURCES[@]}" -eq 0 ]; then
		echo "not generated: no kernel/services/fileserver/fileserver.c in $KERNEL_TREE." >&2
		exit 2
	fi
	INC=(-I"$KERNEL_TREE/kernel/include" -I"$HERE/fileserver_reference/include")
fi

"$CC" -O1 -g -fsanitize=address,undefined "${INC[@]}" \
	"$HERE/fileserver_test.c" "${SOURCES[@]}" -o "$OUT" || {
		echo "compile failed — the implementation does not match fileserver.md" >&2
		exit 1
	}
exec "$OUT"
