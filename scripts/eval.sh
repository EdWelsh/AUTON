#!/usr/bin/env bash
# Score the booted AUTON chat against tests/eval/prompts.jsonl.
#
# Usage: scripts/eval.sh [--model rule|<auton-slm.bin>] [--prompts FILE] [--review] [--json FILE]
#
#   --model rule        boot the rule-engine ISO (default)
#   --model <bin>       build and boot the neural ISO with that flat model
#   --prompts FILE      prompt set (default tests/eval/prompts.jsonl)
#   --review            grade queued answers interactively, then re-score
#   --json FILE         also write the scored results as JSON
#
# Grading is hybrid on purpose (see tests/eval/rubric.md). Prompts with a
# deterministic answer carry an "expect" substring and are graded automatically.
# The rest are free-form; a machine cannot reliably tell CORRECT from GARBAGE
# there, so their answers are queued for a human and the verdict is cached by
# (model fingerprint, prompt id, answer hash). Re-running an unchanged model
# re-uses the cache and asks nothing.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
case "$PY" in /*) ;; *) PY="$ROOT/$PY";; esac

MODEL="rule"
PROMPTS="$ROOT/tests/eval/prompts.jsonl"
REVIEW=0
JSON_OUT=""
CACHE="${EVAL_CACHE:-$ROOT/tests/eval/verdicts.json}"

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
	case "$1" in
		--model)   MODEL="${2:?--model needs a value}"; shift 2 ;;
		--model=*) MODEL="${1#*=}"; shift ;;
		--prompts) PROMPTS="${2:?--prompts needs a value}"; shift 2 ;;
		--prompts=*) PROMPTS="${1#*=}"; shift ;;
		--json)    JSON_OUT="${2:?--json needs a value}"; shift 2 ;;
		--json=*)  JSON_OUT="${1#*=}"; shift ;;
		--review)  REVIEW=1; shift ;;
		-h|--help) usage; exit 0 ;;
		*) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
	esac
done

[ -f "$PROMPTS" ] || { echo "no such prompt set: $PROMPTS" >&2; exit 2; }

# --- pick the ISO ----------------------------------------------------------- #
# AUTON contains no kernel — the agents write it (README.md). Say that plainly
# rather than letting `make` fail with a missing-Makefile error that reads like
# a broken checkout.
KTREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
if [ ! -f "$KTREE/Makefile" ]; then
	echo "no kernel tree at $KTREE — there is nothing to boot." >&2
	echo "  AUTON does not contain a kernel; agents generate one against" >&2
	echo "  agent/kernel_spec/. Scaffold and build a tree with:" >&2
	echo "    agent/tools/build_service.py <service> --tree <dir> --iso" >&2
	echo "  or restore the retired reference:" >&2
	echo "    scripts/kernel-base.sh kernels/x86_64" >&2
	exit 2
fi

if [ "$MODEL" = "rule" ]; then
	ISO="$KTREE/build/auton.iso"
	# Same MEM as the neural path: the neural backend needs >=128M to be
	# selected, and a differing memory size would make the two baselines
	# disagree on "how much memory" for reasons unrelated to the model.
	MEM="${MEM:-256M}"
	make -C "$KTREE" iso >/dev/null 2>&1 || { echo "iso build failed in $KTREE" >&2; exit 1; }
	FINGERPRINT="rule:$(shasum -a 256 "$ROOT/kernels/x86_64/build/kernel.bin" | cut -c1-16)"
else
	case "$MODEL" in /*) ;; *) MODEL="$PWD/$MODEL";; esac
	[ -f "$MODEL" ] || { echo "no such model: $MODEL" >&2; exit 2; }
	ISO="$KTREE/build/auton-neural.iso"
	MEM="${MEM:-256M}"
	make -C "$KTREE" iso-neural MODEL="$MODEL" >/dev/null 2>&1 \
		|| { echo "neural iso build failed" >&2; exit 1; }
	FINGERPRINT="neural:$(shasum -a 256 "$MODEL" | cut -c1-16)"
fi

echo "AUTON eval — model $FINGERPRINT"
echo "prompts: ${PROMPTS#"$ROOT"/}  rubric: tests/eval/rubric.md"

# --- one boot, every prompt ------------------------------------------------- #
# Re-booting per prompt would cost 50 boots; the plan's mitigation is a single
# serial session for the whole set.
ANSWERS="$(mktemp)"
# EVAL_KEEP_LOG=<path> preserves the raw serial capture. A truncated or crashed
# run is only diagnosable from it, and it is deleted on exit by default.
LOG="${EVAL_KEEP_LOG:-$(mktemp)}"
PIPE="$(mktemp -u)"; mkfifo "$PIPE"

# Stock macOS bash is 3.2 — no mapfile. Read portably.
PROMPT_TEXTS=()
while IFS= read -r _line; do
	[ -n "$_line" ] && PROMPT_TEXTS+=("$_line")
done < <("$PY" -c "
import json,sys
for l in open(sys.argv[1]):
    l=l.strip()
    if l: print(json.loads(l)['prompt'])
" "$PROMPTS")

[ "${#PROMPT_TEXTS[@]}" -gt 0 ] || { echo "no prompts parsed from $PROMPTS" >&2; exit 2; }

"$QEMU" -cdrom "$ISO" -serial stdio -display none -no-reboot -m "$MEM" \
	< "$PIPE" > "$LOG" 2>/dev/null &
QPID=$!
# The watchdog has to outlast the whole prompt set, not a typical one. A fixed
# 300s was fine for 50 rule-engine prompts and silently truncated a 65-prompt
# neural run at ses-05: scalar fp32 inference under emulation costs seconds per
# answer, and the last 11 prompts were never sent. Scale it with the prompt
# count and the model, and leave EVAL_TIMEOUT as an override.
if [ "$MODEL" = "rule" ]; then PER_PROMPT="${EVAL_PER_PROMPT:-2}"
else                           PER_PROMPT="${EVAL_PER_PROMPT:-8}"; fi
EVAL_TIMEOUT="${EVAL_TIMEOUT:-$(( 60 + ${#PROMPT_TEXTS[@]} * PER_PROMPT ))}"
echo "watchdog: ${EVAL_TIMEOUT}s for ${#PROMPT_TEXTS[@]} prompts (${PER_PROMPT}s each)"
( sleep "$EVAL_TIMEOUT"; kill -TERM "$QPID" 2>/dev/null ) >/dev/null 2>&1 &
WATCHDOG=$!

# Wait until the machine is back at an idle prompt, i.e. it has finished
# answering. The harness used to send every prompt on a fixed 0.7s cadence and
# then kill QEMU after a 4s drain, which works only while answers are faster
# than the cadence. Neural inference under emulation is not: the machine fell
# behind, was killed mid-queue, and the unsent prompts were scored as garbage —
# a slower model looked like a worse one. Waiting for the answer removes the
# guess entirely.
wait_for_idle() {
	local deadline=$(( $(date +%s) + ${PROMPT_TIMEOUT:-90} ))
	local last=-1 size stable=0
	while [ "$(date +%s)" -lt "$deadline" ]; do
		size=$(wc -c < "$LOG" 2>/dev/null || echo 0)
		if [ "$size" = "$last" ]; then
			stable=$((stable + 1))
			# Idle means the capture ends at a bare prompt with nothing
			# after it. Output still arriving keeps `size` moving.
			#
			# Read into a variable rather than piping into grep: under
			# `pipefail`, grep -q exits on the first match and tail takes
			# SIGPIPE, so the pipeline reports 141 and the match reads as
			# a miss. Every prompt then waited the full timeout, the
			# watchdog killed QEMU, and writing to the dead fifo killed
			# the script with SIGPIPE.
			if [ "$stable" -ge 2 ]; then
				local tailbytes
				tailbytes=$(LC_ALL=C tail -c 32 "$LOG" 2>/dev/null || true)
				case "$tailbytes" in
					# Back at a bare prompt: answered.
					*"auton> ") return 0 ;;
					# A working capability ("install a web server")
					# parks the kernel on "press any key to stop".
					# That is also waiting-for-input, and it cannot
					# reach a prompt until we send the key — waiting
					# for one here deadlocks until the watchdog fires.
					*"key to stop)"*) return 0 ;;
				esac
			fi
			# Safety valve: output has stopped for a while in a state we do
			# not recognise. Waiting the full timeout on every such prompt
			# is how one unrecognised banner turns into a truncated run.
			[ "$stable" -ge "${SETTLE_POLLS:-25}" ] && return 0
		else
			stable=0
		fi
		last="$size"
		sleep "${POLL_GAP:-0.2}"
	done
	return 1
}

exec 3> "$PIPE"
printf '\n' >&3                       # absorbs the byte dropped after UART init
sleep "${BOOT_SETTLE:-3}"
SLOW=0
for p in "${PROMPT_TEXTS[@]}"; do
	# QEMU gone (watchdog fired, or the guest died) means the fifo has no
	# reader and the next write would kill this script with SIGPIPE. Stop
	# cleanly instead; the remaining prompts are reported as NOT_ASKED.
	if ! kill -0 "$QPID" 2>/dev/null; then
		echo "note: guest exited early; $SLOW waits had timed out" >&2
		break
	fi
	printf '%s\n' "$p" >&3
	wait_for_idle || SLOW=$((SLOW + 1))
	# A prompt that starts a working capability ("install a web server") leaves
	# the kernel waiting on "press any key to stop", which would otherwise eat
	# the first byte of the NEXT prompt — its echo then fails to match and a
	# perfectly good answer scores as an empty reply. This blank line is that
	# keypress; at an idle prompt it merely re-prompts.
	printf '\n' >&3
	wait_for_idle || SLOW=$((SLOW + 1))
done
[ "$SLOW" -eq 0 ] || echo "note: $SLOW waits hit PROMPT_TIMEOUT=${PROMPT_TIMEOUT:-90}s"
sleep "${DRAIN_SECS:-2}"
exec 3>&-
kill "$QPID" 2>/dev/null; wait "$QPID" 2>/dev/null || true
kill "$WATCHDOG" 2>/dev/null; wait "$WATCHDOG" 2>/dev/null || true
rm -f "$PIPE"

if [ ! -s "$LOG" ]; then
	echo "no serial output captured" >&2; rm -f "$LOG" "$ANSWERS"; exit 1
fi

# --- extract, grade, score --------------------------------------------------- #
EVAL_LOG="$LOG" EVAL_PROMPTS="$PROMPTS" EVAL_CACHE="$CACHE" \
EVAL_FINGERPRINT="$FINGERPRINT" EVAL_REVIEW="$REVIEW" EVAL_JSON="$JSON_OUT" \
	"$PY" "$ROOT/scripts/lib/eval_score.py"
RC=$?

rm -f "$ANSWERS"
[ -n "${EVAL_KEEP_LOG:-}" ] || rm -f "$LOG"
exit "$RC"
