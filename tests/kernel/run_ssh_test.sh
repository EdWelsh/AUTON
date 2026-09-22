#!/usr/bin/env bash
# Host suite for the SSH service (agent/kernel_spec/services/ssh.md).
#
#   tests/kernel/run_ssh_test.sh --self-test     # against ssh_reference/
#   KERNEL_TREE=<dir> tests/kernel/run_ssh_test.sh
#
# Covers what a host can prove: the binary packet protocol and its refusals,
# name-list negotiation against a real OpenSSH client's recorded KEXINIT, and
# the exchange-hash input against a fixture built independently in Python.
# It proves nothing about the crypto (that is the F12 gate,
# tests/crypto/run_crypto_gate.sh) and nothing about a real session.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/auton_ssh_test"
CC="${CC_HOST:-clang}"
command -v "$CC" >/dev/null 2>&1 || CC=cc
FIXTURES="$HERE/ssh_fixtures"

if [ "${1:-}" = "--self-test" ]; then
	echo "self-test: reference implementation (tests/kernel/ssh_reference/)"
	SOURCES=("$HERE/ssh_reference/ssh_wire.c")
	INC=(-I"$HERE/ssh_reference/include")
else
	KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
	case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
	if [ ! -d "$KERNEL_TREE/kernel" ]; then
		echo "no kernel tree at $KERNEL_TREE — nothing to verify." >&2
		exit 2
	fi
	SOURCES=()
	for c in kernel/services/ssh/ssh_wire.c kernel/services/ssh/wire.c kernel/net/ssh/ssh_wire.c; do
		[ -f "$KERNEL_TREE/$c" ] && SOURCES+=("$KERNEL_TREE/$c")
	done
	if [ "${#SOURCES[@]}" -eq 0 ]; then
		echo "not generated: no kernel/services/ssh/ssh_wire.c in $KERNEL_TREE." >&2
		echo "ssh is specified in agent/kernel_spec/services/ssh.md (status: specified)." >&2
		exit 2
	fi
	INC=(-I"$KERNEL_TREE/kernel/include" -I"$HERE/ssh_reference/include")
fi

"$CC" -O1 -g -D_GNU_SOURCE -fsanitize=address,undefined "${INC[@]}" \
	"$HERE/ssh_test.c" "${SOURCES[@]}" -o "$OUT" || {
		echo "compile failed — the implementation does not match ssh.md's interface" >&2
		exit 1
	}
exec "$OUT" "$FIXTURES"
