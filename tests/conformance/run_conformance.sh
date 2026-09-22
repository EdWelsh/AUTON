#!/usr/bin/env bash
# The conformance harness (hardware-truth H10): does this chip honour its own
# documentation?
#
#   tests/conformance/run_conformance.sh
#
# 1. corpora -> operands (agent/tools/conformance.py; decimals become bits on
#    the host, in Python, so no host FP touches an expected answer)
# 2. operands -> oracle  (Berkeley SoftFloat, integer arithmetic only)
# 3. oracle vs this CPU  (native_semantic: divsd/sqrtsd; native_fault: #UD)
# 4. verdicts -> summary (per clause, with zero published as a finding)
#
# On a host that is not x86-64 the native venues print SKIP and the run still
# builds the oracle — an oracle that cannot be built is a broken harness, and
# that must fail even where the instructions cannot run. Exit 0 pass or skip,
# 1 divergence, 2 the harness itself is broken.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
BUILD="${BUILD_DIR:-${TMPDIR:-/tmp}/auton_conformance}"
PY="${PY:-$ROOT/.venv/bin/python}"
[ -x "$PY" ] || PY=python3
CC="${CC_HOST:-clang}"
command -v "$CC" >/dev/null 2>&1 || CC=cc
mkdir -p "$BUILD"

SF="$(bash "$ROOT/scripts/fetch-softfloat.sh" | sed 's/^softfloat: //')"
case "$SF" in /*) ;; *) SF="$ROOT/$SF";; esac
[ -d "$SF/source" ] || { echo "softfloat sources missing at $SF" >&2; exit 2; }

echo "== corpora -> operands"
"$PY" "$ROOT/agent/tools/conformance.py" --operands "$BUILD" || exit 2

echo "== building the oracle (SoftFloat)"
# The rule is that no host floating point may touch an expected answer, and
# SoftFloat satisfies it by construction: not one of its source files declares
# a C `float` or `double` (float64_t is a struct wrapping uint64_t), so its
# arithmetic is integer code and its optimisation level cannot change a result.
#
# It is therefore built at its own -O2. Forcing -O0 does not make it safer and
# does break it: with INLINE_LEVEL=5 the inline primitives are never emitted
# and the link fails on softfloat_countLeadingZeros64.
#
# What does get -O0 -ffp-contract=off is everything BELOW that touches operands:
# gen_oracle.c and the native venues, where a compiler could otherwise fold the
# very arithmetic under test.
SF_LIB="$BUILD/softfloat.a"
if [ ! -f "$SF_LIB" ]; then
	# COMPILE_C ends with `-o $@`, which make expands per object; the single
	# quotes keep $@ out of this shell.
	( cd "$SF/build/Linux-x86_64-GCC" && make -s clean >/dev/null 2>&1;
	  cd "$SF/build/Linux-x86_64-GCC" && make -s -j4 \
		COMPILE_C="$CC -c -Werror-implicit-function-declaration -DSOFTFLOAT_FAST_INT64 -DSOFTFLOAT_ROUND_ODD -DINLINE_LEVEL=5 -I. -I../../source/8086-SSE -I../../source/include -O2 "'-o $@' \
		>"$BUILD/softfloat-build.log" 2>&1 ) || {
			echo "softfloat build failed:" >&2
			tail -15 "$BUILD/softfloat-build.log" >&2
			exit 2
		}
	cp "$SF/build/Linux-x86_64-GCC/softfloat.a" "$SF_LIB"
fi

"$CC" -O0 -ffp-contract=off -I"$SF/source/include" -I"$SF/build/Linux-x86_64-GCC" \
	-I"$SF/source/8086-SSE" "$HERE/gen_oracle.c" "$SF_LIB" -o "$BUILD/gen_oracle" || exit 2

# The oracle's own check, before it is trusted to judge anything: the Pentium
# FDIV operands must produce the correct quotient's bits.
printf 'oracle-selftest f64_div near_even 4150017ec0000000 4147ffff80000000\n' \
	>"$BUILD/selftest.txt"
"$BUILD/gen_oracle" "$BUILD/selftest.txt" "$BUILD/selftest.out" 2>/dev/null
if ! grep -q "3ff557541c7c6b43" "$BUILD/selftest.out"; then
	echo "ORACLE SELF-TEST FAILED: f64_div(4195835, 3145727) is not the known quotient" >&2
	cat "$BUILD/selftest.out" >&2
	exit 2
fi
echo "   oracle self-test: f64_div(4195835, 3145727) = 3ff557541c7c6b43 (correct)"

"$BUILD/gen_oracle" "$BUILD/operands.txt" "$BUILD/oracle.txt" || exit 2

echo "== this CPU"
: >"$BUILD/verdicts.txt"
# The identity a divergence would be filed against: vendor and
# family:model:stepping, not a brand string. disclosure.py refuses anything
# vaguer, because "some Intel chips" is not a finding.
VENDOR="$(grep -m1 vendor_id /proc/cpuinfo 2>/dev/null | cut -d: -f2- | sed 's/^ //')"
FAMILY="$(grep -m1 'cpu family' /proc/cpuinfo 2>/dev/null | cut -d: -f2- | tr -d ' ')"
MODEL="$(grep -m1 '^model[^ ]*	' /proc/cpuinfo 2>/dev/null | cut -d: -f2- | tr -d ' ')"
STEP="$(grep -m1 stepping /proc/cpuinfo 2>/dev/null | cut -d: -f2- | tr -d ' ')"
BRAND="$(sysctl -n machdep.cpu.brand_string 2>/dev/null || \
	grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2- | sed 's/^ //' || echo unknown)"
FMS=""
[ -n "$FAMILY" ] && [ -n "$MODEL" ] && [ -n "$STEP" ] && FMS="$FAMILY:$MODEL:$STEP"
echo "IDENTITY ${VENDOR:+$VENDOR }${FMS:+$FMS }$(uname -m) $BRAND" >>"$BUILD/verdicts.txt"

"$CC" -O1 -g "$HERE/native_semantic.c" -o "$BUILD/native_semantic" || exit 2
"$CC" -O1 -g "$HERE/native_fault.c" -o "$BUILD/native_fault" || exit 2
"$BUILD/native_semantic" "$BUILD/operands.txt" "$BUILD/oracle.txt" >>"$BUILD/verdicts.txt"
sem=$?
"$BUILD/native_fault" "$BUILD/faults.txt" >>"$BUILD/verdicts.txt"
flt=$?

echo "== verdicts"
"$PY" "$ROOT/agent/tools/conformance.py" --summarise "$BUILD/verdicts.txt"
rc=$?
echo "   verdicts: ${BUILD}/verdicts.txt"
[ "$sem" -eq 2 ] || [ "$flt" -eq 2 ] && exit 2
exit "$rc"
