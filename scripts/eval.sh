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
if [ "$MODEL" = "rule" ]; then
	ISO="$ROOT/kernels/x86_64/build/auton.iso"
	# Same MEM as the neural path: the neural backend needs >=128M to be
	# selected, and a differing memory size would make the two baselines
	# disagree on "how much memory" for reasons unrelated to the model.
	MEM="${MEM:-256M}"
	make -C "$ROOT/kernels/x86_64" iso >/dev/null 2>&1 || { echo "build failed" >&2; exit 1; }
	FINGERPRINT="rule:$(shasum -a 256 "$ROOT/kernels/x86_64/build/kernel.bin" | cut -c1-16)"
else
	case "$MODEL" in /*) ;; *) MODEL="$PWD/$MODEL";; esac
	[ -f "$MODEL" ] || { echo "no such model: $MODEL" >&2; exit 2; }
	ISO="$ROOT/kernels/x86_64/build/auton-neural.iso"
	MEM="${MEM:-256M}"
	make -C "$ROOT/kernels/x86_64" iso-neural MODEL="$MODEL" >/dev/null 2>&1 \
		|| { echo "neural iso build failed" >&2; exit 1; }
	FINGERPRINT="neural:$(shasum -a 256 "$MODEL" | cut -c1-16)"
fi

echo "AUTON eval — model $FINGERPRINT"
echo "prompts: ${PROMPTS#"$ROOT"/}  rubric: tests/eval/rubric.md"

# --- one boot, every prompt ------------------------------------------------- #
# Re-booting per prompt would cost 50 boots; the plan's mitigation is a single
# serial session for the whole set.
ANSWERS="$(mktemp)"
LOG="$(mktemp)"
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
( sleep "${EVAL_TIMEOUT:-300}"; kill -TERM "$QPID" 2>/dev/null ) >/dev/null 2>&1 &
WATCHDOG=$!

exec 3> "$PIPE"
printf '\n' >&3                       # absorbs the byte dropped after UART init
sleep "${BOOT_SETTLE:-3}"
for p in "${PROMPT_TEXTS[@]}"; do
	printf '%s\n' "$p" >&3
	sleep "${SEND_GAP:-0.4}"
	# A prompt that starts a working capability ("install a web server") leaves
	# the kernel waiting on "press any key to stop", which would otherwise eat
	# the first byte of the NEXT prompt — its echo then fails to match and a
	# perfectly good answer scores as an empty reply. This blank line is that
	# keypress; at an idle prompt it merely re-prompts.
	printf '\n' >&3
	sleep "${STOP_GAP:-0.3}"
done
sleep "${DRAIN_SECS:-4}"
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

rm -f "$LOG" "$ANSWERS"
exit "$RC"
