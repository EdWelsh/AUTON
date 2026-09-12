#!/usr/bin/env bash
# Run one long unscripted session against the booted OS and analyse it.
#
# Usage: scripts/session.sh [--model rule|<auton-slm.bin>] [--label NAME]
#
# Phase 7's automated stand-in for a 20-minute human session. A Phase 6 eval
# scores 50 independent single-shot answers; this drives one continuous session
# and checks what only appears over duration and state:
#
#   consistency   the same question far apart gets the same answer
#   statefulness  a change made early still holds late
#   stability     answers do not degrade as the session grows
#   novelty       input nobody anticipated (gemma4-generated, filtered against
#                 both the eval set and the training corpus)
#
# What this does NOT reproduce is a person's surprise. See the phase report.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
case "$PY" in /*) ;; *) PY="$ROOT/$PY";; esac

MODEL="rule"
LABEL=""
TURNS_SRC=""
REPLAY=""
while [ $# -gt 0 ]; do
	case "$1" in
		--model) MODEL="${2:?--model needs a value}"; shift 2 ;;
		--model=*) MODEL="${1#*=}"; shift ;;
		--label) LABEL="${2:?--label needs a value}"; shift 2 ;;
		--turns) TURNS_SRC="${2:?--turns needs a value}"; shift 2 ;;
		--replay) REPLAY="${2:?--replay needs a previous session dir}"; shift 2 ;;
		--label=*) LABEL="${1#*=}"; shift ;;
		-h|--help) sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
		*) echo "unknown argument: $1" >&2; exit 2 ;;
	esac
done

if [ "$MODEL" = "rule" ]; then
	ISO="$ROOT/kernels/x86_64/build/auton.iso"
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

STAMP="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
OUT="$ROOT/.artifacts/sessions/${LABEL:-session}-$STAMP"
mkdir -p "$OUT"
TRANSCRIPT="$OUT/transcript.log"

echo "session: ${LABEL:-unlabelled}"
echo "model:   $FINGERPRINT"
echo "out:     ${OUT#"$ROOT"/}"

# Turn plan. --replay reuses a previous session's plan verbatim, which is the
# only way to compare two rungs on identical input: the planner filters against
# the eval set, and that set grows as findings are promoted, so a fresh plan is
# not the same plan a week later.
if [ -n "$REPLAY" ]; then
	[ -f "$REPLAY/turns.json" ] || { echo "no turns.json in $REPLAY" >&2; exit 2; }
	cp "$REPLAY/turns.json" "$OUT/turns.json"
	"$PY" -c "import json; print(len(json.load(open('$OUT/turns.json'))))" > "$OUT/.count"
	echo "replay:  ${REPLAY##*/}"
else
	"$PY" -c "
import sys, json, pathlib; sys.path.insert(0, '$ROOT/scripts/lib')
import session_probe as sp
src = '$TURNS_SRC'
turns = sp.plan_turns(generated_path=pathlib.Path(src) if src else None)
json.dump(turns, open('$OUT/turns.json','w'), indent=2)
print(len(turns))
" > "$OUT/.count" || { echo "turn planning failed" >&2; exit 1; }
fi
echo "turns:   $(cat "$OUT/.count")"
echo

PIPE="$(mktemp -u)"; mkfifo "$PIPE"
"$QEMU" -cdrom "$ISO" -serial stdio -display none -no-reboot -m "$MEM" \
	< "$PIPE" > "$TRANSCRIPT" 2>/dev/null &
QPID=$!
( sleep "${SESSION_TIMEOUT:-1500}"; kill -TERM "$QPID" 2>/dev/null ) >/dev/null 2>&1 &
WATCHDOG=$!

exec 3> "$PIPE"
printf '\n' >&3                      # absorbs the byte dropped after UART init
sleep "${BOOT_SETTLE:-3}"
while IFS= read -r line; do
	printf '%s\n' "$line" >&3
	sleep "${SEND_GAP:-1.2}"
	printf '\n' >&3                  # absorbs "press any key" from role commands
	sleep "${STOP_GAP:-0.4}"
done < <("$PY" -c "
import sys, json; sys.path.insert(0,'$ROOT/scripts/lib')
for t in json.load(open('$OUT/turns.json')): print(t['text'])
")
sleep "${DRAIN_SECS:-6}"
exec 3>&-
kill "$QPID" 2>/dev/null; wait "$QPID" 2>/dev/null || true
kill "$WATCHDOG" 2>/dev/null; wait "$WATCHDOG" 2>/dev/null || true
rm -f "$PIPE" "$OUT/.count"

[ -s "$TRANSCRIPT" ] || { echo "no transcript captured" >&2; exit 1; }

SESSION_OUT="$OUT" SESSION_FINGERPRINT="$FINGERPRINT" "$PY" - <<'PYEOF'
import json, os, sys
sys.path.insert(0, os.path.join(os.environ.get("ROOT", "."), "scripts", "lib"))
sys.path.insert(0, "scripts/lib")
import session_probe as sp

out = os.environ["SESSION_OUT"]
turns = json.load(open(f"{out}/turns.json"))
log = open(f"{out}/transcript.log", errors="replace").read()
answers = sp.extract(log, turns)
report = sp.analyse(turns, answers)
report["fingerprint"] = os.environ["SESSION_FINGERPRINT"]
json.dump({"report": report,
           "turns": [{**t, "answer": answers.get(t["n"], "")} for t in turns]},
          open(f"{out}/session.json", "w"), indent=2)

print(f"answered {report['answered']}/{report['turns']} turns\n")
ok = True
for f in report["findings"]:
    mark = "PASS" if f["ok"] else "FAIL"
    ok &= f["ok"]
    print(f"{mark}  {f['property']:<14} {f['detail']}")

empty = [n for n in report["novel"] if n["empty"]]
fell = [n for n in report["novel"] if n["fell_back"] and not n["empty"]]
print(f"\nnovel input: {len(report['novel'])} turns  "
      f"({len(fell)} declined, {len(empty)} unanswered)")
print("\nSESSION: ALL PASS" if ok else "\nSESSION: FAILURES")
sys.exit(0 if ok else 1)
PYEOF
