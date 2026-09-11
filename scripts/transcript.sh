#!/usr/bin/env bash
# Drive the booted AUTON chat with a list of sentences and assert each reply.
#
# Usage: scripts/transcript.sh <expectations.txt> [iso] [serial-log-out]
#
# The expectations file holds "<sentence> :: <expected substring>" lines
# (# comments and blanks ignored). Sentences are sent in order to one boot, and
# each expectation is matched ONLY inside that sentence's reply block — the
# lines between its echo and the next "auton>" prompt. A global grep would let
# a later answer satisfy an earlier expectation and would not notice the chat
# replying to the wrong question.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"

EXPECT="${1:?expectations file}"
ISO="${2:-$ROOT/kernels/x86_64/build/auton.iso}"
SERIAL_OUT="${3:-}"

[ -f "$EXPECT" ] || { echo "no such expectations file: $EXPECT" >&2; exit 2; }
[ -f "$ISO" ]    || { echo "no such iso: $ISO" >&2; exit 2; }

# --- parse expectations ----------------------------------------------------- #
SENTENCES=(); EXPECTED=()
while IFS= read -r line; do
	case "$line" in ''|'#'*) continue ;; esac
	[ "$line" = "${line%% :: *}" ] && continue      # no separator -> not a pair
	SENTENCES+=("${line%% :: *}")
	EXPECTED+=("${line#* :: }")
done < "$EXPECT"

TOTAL="${#SENTENCES[@]}"
[ "$TOTAL" -gt 0 ] || { echo "no expectations found in $EXPECT" >&2; exit 2; }

# --- drive one boot --------------------------------------------------------- #
LOG="$(mktemp)"
PIPE="$(mktemp -u)"
mkfifo "$PIPE" || { echo "could not create input fifo" >&2; exit 1; }

# QEMU is fed through a fifo and stopped once the replies have drained. Piping
# stdin directly would leave it running until the timeout expired — it does not
# exit when its input closes — which cost two minutes per run for nothing.
"$QEMU" -cdrom "$ISO" -serial stdio -display none -no-reboot \
	-m "${MEM:-128M}" < "$PIPE" > "$LOG" 2>/dev/null &
QPID=$!

# Watchdog: if the VM wedges, do not hang the harness. Its own stdout is
# detached — otherwise the orphaned sleep keeps this script's stdout open and
# any caller reading our output (a pipe, e2e.sh) blocks until the full timeout,
# which defeats the point of stopping QEMU early.
( sleep "${CHAT_TIMEOUT:-120}"; kill -TERM "$QPID" 2>/dev/null ) >/dev/null 2>&1 &
WATCHDOG=$!

# The leading blank line absorbs the byte QEMU drops after UART init (see
# run-acceptance.sh). Sentences are paced so each reply lands before the next.
exec 3> "$PIPE"
printf '\n' >&3
sleep "${BOOT_SETTLE:-3}"
for s in "${SENTENCES[@]}"; do
	printf '%s\n' "$s" >&3
	sleep "${SEND_GAP:-0.4}"
done
sleep "${DRAIN_SECS:-4}"
exec 3>&-

kill "$QPID" 2>/dev/null; wait "$QPID" 2>/dev/null || true
kill "$WATCHDOG" 2>/dev/null; wait "$WATCHDOG" 2>/dev/null || true
rm -f "$PIPE"

[ -n "$SERIAL_OUT" ] && cp "$LOG" "$SERIAL_OUT"

if [ ! -s "$LOG" ]; then
	echo "no serial output captured" >&2
	rm -f "$LOG"; exit 1
fi

# --- match each reply in its own block -------------------------------------- #
mapfile -t LINES < "$LOG" 2>/dev/null || { while IFS= read -r l; do LINES+=("$l"); done < "$LOG"; }

pos=0
fail=0
npass=0
for i in "${!SENTENCES[@]}"; do
	sentence="${SENTENCES[$i]}"
	expected="${EXPECTED[$i]}"

	# Find this sentence's echo at or after the current position.
	# Anchor to the prompt echo, not a bare substring: the boot banner and the
	# help listing both quote example commands ("help", "what is pci 8086:100e"),
	# and matching those would test the wrong block entirely.
	echo_at=-1
	for ((j=pos; j<${#LINES[@]}; j++)); do
		case "${LINES[$j]}" in *"auton> $sentence"*) echo_at=$j; break ;; esac
	done
	if [ "$echo_at" -lt 0 ]; then
		printf 'FAIL  %-34s (sentence never echoed)\n' "$sentence"
		fail=1; continue
	fi

	# Reply block: up to the next prompt.
	found=0
	for ((j=echo_at+1; j<${#LINES[@]}; j++)); do
		case "${LINES[$j]}" in *"auton>"*) break ;; esac
		case "${LINES[$j]}" in *"$expected"*) found=1; break ;; esac
	done

	if [ "$found" -eq 1 ]; then
		printf 'PASS  %-34s -> %s\n' "$sentence" "$expected"
		npass=$((npass + 1))
	else
		printf 'FAIL  %-34s expected %s\n' "$sentence" "$expected"
		printf '      got: %s\n' "$(sed -n "$((echo_at+2))p" "$LOG")"
		fail=1
	fi
	pos=$((echo_at + 1))
done

rm -f "$LOG"
echo "TRANSCRIPT: $npass/$TOTAL"
[ "$fail" -eq 0 ] || exit 1
echo "TRANSCRIPT: ALL PASS"
