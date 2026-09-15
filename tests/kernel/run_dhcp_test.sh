#!/usr/bin/env bash
# Compile and run the DHCP server tests on the host.
#
#   KERNEL_TREE=kernels/x86_64 tests/kernel/run_dhcp_test.sh
#
# dhcp.md splits dhcp_handle from dhcp_serve so the packet path is reachable
# without a NIC. The cases that matter most — a malformed option length, an
# exhausted pool — are the ones a live client never produces.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/auton_dhcp_test"

SRC="$KERNEL_TREE/kernel/services/dhcp/server.c"
if [ ! -f "$SRC" ]; then
	echo "no DHCP server at $SRC." >&2
	echo "Specified in agent/kernel_spec/services/dhcp.md; not generated here." >&2
	exit 2
fi

# The stub headers stand in for the kernel's net/kstr/kernel headers, so the
# test links without the rest of the kernel. The real header is the tree's.
clang -O1 -g -fsanitize=address,undefined \
	-I"$HERE/dhcp_stub/include" -I"$KERNEL_TREE/kernel/include" \
	"$HERE/dhcp_test.c" "$SRC" -o "$OUT" || {
		echo "compile failed — the server does not match dhcp.md's interface" >&2
		exit 1
	}
exec "$OUT"
