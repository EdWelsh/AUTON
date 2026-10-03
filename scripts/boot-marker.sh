#!/usr/bin/env bash
# Boot a kernel tree's plain ISO and wait for one serial marker.
#
#   scripts/boot-marker.sh <tree> <regex> [timeout=90]
#
# Builds the tree's ISO first with the cross toolchain (a fresh tree has no
# build/, and host clang cannot build it). Exit 0 when a serial line matches
# <regex>; 1 when the build fails or the kernel boots (or stops) without it;
# 2 when there is no kernel tree. The serial log is
# printed either way, so a gate's archived tail shows what the kernel said.
#
# A campaign gate for "the kernel boots and reports X" (R1's [MM] line, R10's
# F00F line). It replaces `scripts/e2e.sh ... | grep`, which trains, exports
# and checks parity for the SLM before it boots anything: when the SLM side
# broke (the base tree fails parity too), every such gate failed on a kernel
# it never booted (w18 R1, stop rule 5).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TREE="${1:?usage: boot-marker.sh <tree> <regex> [timeout]}"
PATTERN="${2:?usage: boot-marker.sh <tree> <regex> [timeout]}"
LIMIT="${3:-90}"
ISO="$TREE/build/auton.iso"

# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"
auton_accel "${AUTON_ACCEL:-}" >/dev/null || exit 2

[ -d "$TREE/kernel" ] || { echo "no kernel tree at $TREE" >&2; exit 2; }
if ! make -C "$TREE" iso >"$TREE/.boot-marker-build.log" 2>&1; then
	tail -20 "$TREE/.boot-marker-build.log"
	echo "boot-marker: the ISO did not build"
	exit 1
fi
[ -f "$ISO" ] || { echo "boot-marker: the build made no $ISO"; exit 1; }

LOG="$(mktemp -t boot-marker)"
trap 'rm -f "$LOG"' EXIT
"$QEMU" -accel "$AUTON_ACCEL" -cdrom "$ISO" -serial stdio -display none \
	-no-reboot -m "${MEM:-256M}" > "$LOG" 2>/dev/null &
qemu_pid=$!

found=1 waited=0
while [ "$waited" -lt "$LIMIT" ]; do
	if grep -aqE "$PATTERN" "$LOG"; then found=0; break; fi
	kill -0 "$qemu_pid" 2>/dev/null || break
	sleep 1
	waited=$((waited + 1))
done
kill "$qemu_pid" 2>/dev/null
wait "$qemu_pid" 2>/dev/null || true

cat "$LOG"
if [ "$found" -eq 0 ]; then
	echo "boot-marker: found /$PATTERN/ after ${waited}s"
else
	echo "boot-marker: no line matched /$PATTERN/ in ${waited}s"
fi
exit "$found"
