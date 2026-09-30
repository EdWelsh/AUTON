#!/usr/bin/env bash
# The play-doom gate suite (services/play-doom.md, "Host-test interface"),
# frozen before any generation run (R12).
#
#   tests/kernel/run_play_doom_test.sh --self-test   # against play_doom_reference/
#   tests/kernel/run_play_doom_test.sh --inject      # score: every injected bug caught?
#   KERNEL_TREE=<dir> tests/kernel/run_play_doom_test.sh
#
# exit 2 = not generated, 1 = generated wrong (or a bug the suite missed), 0 = pass.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
CC="${CC_HOST:-clang}"
command -v "$CC" >/dev/null 2>&1 || CC=cc
FLAGS=(-O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all -std=c11 -Wall)
REF="$HERE/play_doom_reference"
OUT="${TMPDIR:-/tmp}/auton_play_doom_test"
BUGS=10

build() {  # build <out> <include dir> <source> [defines...]
	local out="$1" inc="$2" src="$3"; shift 3
	"$CC" "${FLAGS[@]}" "$@" -I"$inc" "$HERE/play_doom_test.c" "$src" -o "$out"
}

case "${1:-}" in
--self-test)
	echo "self-test: reference implementation (tests/kernel/play_doom_reference/)"
	build "$OUT" "$REF/include" "$REF/platform_pure.c" || exit 1
	exec "$OUT"
	;;
--inject)
	# A suite is only evidence if it can fail. Each BUG_n is one defect a
	# plausible platform layer could ship with; every one must be caught.
	caught=0
	for n in $(seq 1 "$BUGS"); do
		build "$OUT.bug$n" "$REF/include" "$REF/platform_pure.c" "-DBUG_$n" 2>/dev/null \
			|| { echo "BUG_$n: did not compile — a broken bug is not a caught one"; continue; }
		if "$OUT.bug$n" >/dev/null 2>&1; then
			echo "BUG_$n: MISSED"
		else
			echo "BUG_$n: caught"
			caught=$((caught + 1))
		fi
	done
	echo "injected-bug score: $caught/$BUGS"
	[ "$caught" -eq "$BUGS" ]
	exit $?
	;;
esac

KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
SRC="$KERNEL_TREE/kernel/services/play_doom/platform_pure.c"
if [ ! -f "$SRC" ]; then
	echo "no $SRC: the play-doom platform layer is specified in services/play-doom.md" >&2
	echo "and not generated into this tree. Run --self-test to check the suite." >&2
	exit 2
fi
build "$OUT" "$KERNEL_TREE/kernel/include" "$SRC" || {
	echo "compile failed: platform_pure.c does not match play-doom.md's host-test interface" >&2
	exit 1
}
exec "$OUT"
