#!/usr/bin/env bash
# The F12 crypto gate: six primitives x four criteria.
#
#   tests/crypto/run_crypto_gate.sh
#
# Criteria (agent/kernel_spec/decisions/ssh-crypto.md, committed first):
#   a vetted source   — judged by a person, cited in the decision record
#   b freestanding    — x86_64-elf-gcc -ffreestanding -nostdlib -fno-builtin -O2,
#                       undefined symbols a subset of {memcpy, memset}
#   c vectors         — RFC/NIST vectors, on the host, under ASan+UBSan
#   d licence         — licences.yaml, permitted, not depends_on_use
#
# This script judges (b) and (c). Exit 0 both pass, 1 a failure, 2 the sources
# are not in .cache/vendor/crypto (see the decision record for how they arrive).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/.cache/vendor/crypto"
MC="$SRC/Monocypher-4.0.2/src"
BR="$SRC/bearssl"
OUT="${TMPDIR:-/tmp}/auton_crypto_gate"
mkdir -p "$OUT"

for f in "$MC/monocypher.c" "$MC/optional/monocypher-ed25519.c" "$BR/src/sha2small.c" \
		"$BR/src/codec/enc32be.c" "$BR/src/codec/dec32be.c"; do
	[ -f "$f" ] || { echo "missing $f — fetch the sources first (decision record)" >&2; exit 2; }
done

CC_HOST="${CC_HOST:-clang}"
command -v "$CC_HOST" >/dev/null || CC_HOST=cc
CROSS="${CC:-x86_64-elf-gcc}"
INCS=(-I"$MC" -I"$MC/optional" -I"$BR/inc" -I"$BR/src")
# BearSSL's inner.h includes <string.h> for memcpy/memset, which a kernel
# supplies itself. The stub declares only those (plus the few a C library
# guarantees), so needing anything more is a compile error, which is the answer.
FREESTANDING=(-I"$(dirname "$0")/freestanding_stub")

fail=0

echo "(b) freestanding compile, undefined symbols in {memcpy, memset}"
if ! command -v "$CROSS" >/dev/null; then
	echo "  SKIP  no $CROSS on PATH (criterion b unjudged)"
	fail=1
else
	objs=()
	for unit in "$MC/monocypher.c" "$MC/optional/monocypher-ed25519.c" "$BR/src/sha2small.c" \
		"$BR/src/codec/enc32be.c" "$BR/src/codec/dec32be.c"; do
		name="$(basename "$unit")"
		obj="$OUT/${name%.c}.o"
		if ! "$CROSS" -ffreestanding -nostdlib -fno-builtin -O2 -c \
			"${FREESTANDING[@]}" "${INCS[@]}" "$unit" -o "$obj" 2>"$OUT/$name.log"; then
			echo "  FAIL  $name does not compile freestanding:"
			sed 's/^/        /' "$OUT/$name.log" | head -5
			fail=1
			continue
		fi
		echo "  PASS  $name compiles freestanding"
		objs+=("$obj")
	done
	# The symbols are judged over the LINKED SET, not per object: one unit
	# calling another's function is internal, and only what the set still
	# needs from outside is what a kernel would have to provide.
	if [ "${#objs[@]}" -eq 5 ]; then
		x86_64-elf-ld -r -o "$OUT/crypto.o" "${objs[@]}" 2>/dev/null
		undef="$(x86_64-elf-nm -u "$OUT/crypto.o" 2>/dev/null | awk '{print $2}' | sort -u)"
		extra="$(echo "$undef" | grep -vE '^(memcpy|memset)$' | tr '\n' ' ')"
		if [ -n "${extra// /}" ]; then
			echo "  FAIL  the set needs beyond {memcpy, memset}: $extra"
			fail=1
		else
			echo "  PASS  the set's undefined symbols: $(echo "$undef" | tr '\n' ' ')"
		fi
	fi
fi

echo
echo "(c) published vectors, host build under ASan+UBSan"
BIN="$OUT/vectors"
if ! "$CC_HOST" -O1 -g -fsanitize=address,undefined "${INCS[@]}" \
	"$(dirname "$0")/vectors.c" "$MC/monocypher.c" "$MC/optional/monocypher-ed25519.c" \
	"$BR/src/sha2small.c" "$BR/src/codec/enc32be.c" "$BR/src/codec/dec32be.c" -o "$BIN" 2>"$OUT/vectors.log"; then
	echo "  FAIL  the vector harness does not build:"
	sed 's/^/        /' "$OUT/vectors.log" | head -15
	exit 1
fi
"$BIN" || fail=1

echo
[ "$fail" -eq 0 ] && echo "crypto gate (b,c): PASS" || echo "crypto gate (b,c): FAIL"
exit "$fail"
