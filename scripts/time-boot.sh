#!/usr/bin/env bash
# Time boots of an ISO to its [BOOT] OK marker.
#
#   scripts/time-boot.sh <iso> [runs=3] [--accel NAME]
#
# Prints one line per run and a summary with the accelerator, QEMU version and
# CPU, so a number is never recorded without what produced it. One end of the
# windows-linux B1 ratio (KVM vs TCG on the same ISO); see docs/HOST-MATRIX.md.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"

ISO="${1:?usage: time-boot.sh <iso> [runs] [--accel NAME]}"; shift
RUNS=3 REQ=""
while [ $# -gt 0 ]; do
	case "$1" in
		--accel) REQ="${2:?--accel needs a value}"; shift 2 ;;
		--accel=*) REQ="${1#*=}"; shift ;;
		*) RUNS="$1"; shift ;;
	esac
done
[ -f "$ISO" ] || { echo "no ISO at $ISO" >&2; exit 2; }
auton_accel "$REQ" || exit 2
LIMIT="${BOOT_TIMEOUT:-120}"

now() { python3 -c 'import time; print(time.time())'; }
cpu() {
	case "$(uname -s)" in
		Darwin) sysctl -n machdep.cpu.brand_string ;;
		*) grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2- | sed 's/^ //' ;;
	esac
}

total=0
for i in $(seq 1 "$RUNS"); do
	log="$(mktemp)"
	start="$(now)"
	"$QEMU" -accel "$AUTON_ACCEL" -cdrom "$ISO" -serial stdio -display none \
		-no-reboot -m "${MEM:-128M}" >"$log" 2>&1 &
	pid=$!
	ok=0
	while kill -0 "$pid" 2>/dev/null; do
		grep -q '\[BOOT\] OK' "$log" && { ok=1; break; }
		python3 -c "import sys,time; sys.exit(0 if time.time()-$start < $LIMIT else 1)" || break
		sleep 0.05
	done
	end="$(now)"
	kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
	secs="$(python3 -c "print(f'{$end-$start:.2f}')")"
	if [ "$ok" = 1 ]; then
		echo "run $i: ${secs}s"
		total="$(python3 -c "print($total+$secs)")"
	else
		echo "run $i: no [BOOT] OK within ${LIMIT}s" >&2
		tail -5 "$log" >&2
		rm -f "$log"; exit 1
	fi
	rm -f "$log"
done
echo "mean: $(python3 -c "print(f'{$total/$RUNS:.2f}')")s over $RUNS runs"
echo "accel: $AUTON_ACCEL ($AUTON_ACCEL_REASON)"
echo "qemu: $("$QEMU" --version | head -1)"
echo "cpu: $(cpu)"
