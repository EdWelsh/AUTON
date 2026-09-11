#!/usr/bin/env bash
# The AUTON end-to-end spine: train -> export -> parity -> ISO -> boot ->
# markers -> transcript, in one command, with a verdict and an artifact dir.
#
# Usage: scripts/e2e.sh [--rung 3a] [--skip-train] [--keep N] [--help]
#
#   --rung {3a,3b,3c}  training rung (default 3a: tiny model, existing corpus)
#   --skip-train       reuse the last checkpoint in SLM/work (fast iteration)
#   --keep N           artifact dirs to retain (default 10)
#
# Exits non-zero on the first failing stage. Artifacts are written either way.
#
# Hard rule: this script CALLS existing entry points and never reimplements
# them. Any logic a stage needs belongs in the tool that stage invokes.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"
# shellcheck source=lib/markers.sh
source "$ROOT/scripts/lib/markers.sh"

PY="${PYTHON:-$ROOT/.venv/bin/python}"
case "$PY" in /*) ;; *) PY="$ROOT/$PY";; esac   # absolutize before any cd

ARCH="${ARCH:-x86_64}"
RUNG="3a"
SKIP_TRAIN=0
KEEP="${KEEP:-10}"

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
	case "$1" in
		--rung)       RUNG="${2:?--rung needs a value}"; shift 2 ;;
		--rung=*)     RUNG="${1#*=}"; shift ;;
		--skip-train) SKIP_TRAIN=1; shift ;;
		--keep)       KEEP="${2:?--keep needs a value}"; shift 2 ;;
		--keep=*)     KEEP="${1#*=}"; shift ;;
		-h|--help)    usage; exit 0 ;;
		*) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
	esac
done

case "$RUNG" in
	3a) ;;
	3b|3c)
		echo "rung $RUNG is not implemented yet (Phase $RUNG delivers it)." >&2
		echo "Only --rung 3a runs today." >&2
		exit 2 ;;
	*) echo "unknown rung: $RUNG (expected 3a, 3b or 3c)" >&2; exit 2 ;;
esac

# --- artifacts -------------------------------------------------------------- #
RUN_ID="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
ART="$ROOT/.artifacts/e2e/$RUN_ID"
mkdir -p "$ART"

WORK="$ROOT/SLM/work"
STAGE_LOG="$ART/stages.tsv"
printf 'stage\tname\tstatus\tseconds\n' > "$STAGE_LOG"

TOTAL_STAGES=7
STAGE_NO=0
FAILED_STAGE=""
declare -a STAGE_NAMES=()
declare -a STAGE_STATUS=()
declare -a STAGE_SECS=()

# stage <name> <function> [args...]
# Runs a stage, times it, records it, and short-circuits the rest on failure.
# A stage that is skipped still appears in the summary — a silent skip and a
# pass must never look alike.
stage() {
	local name="$1"; shift
	STAGE_NO=$((STAGE_NO + 1))
	local label
	label="$(printf '[%d/%d] %-10s' "$STAGE_NO" "$TOTAL_STAGES" "$name")"

	if [ -n "$FAILED_STAGE" ]; then
		printf '%s SKIPPED (after %s failed)\n' "$label" "$FAILED_STAGE"
		record_stage "$name" SKIPPED 0
		return 0
	fi

	local start end secs rc
	start="$(date +%s)"
	printf '%s ... ' "$label"
	if "$@" > "$ART/$STAGE_NO-$name.log" 2>&1; then rc=0; else rc=$?; fi
	end="$(date +%s)"
	secs=$((end - start))

	if [ "$rc" -eq 0 ]; then
		printf 'ok (%ss)\n' "$secs"
		record_stage "$name" PASS "$secs"
	else
		printf 'FAILED (%ss, rc=%s)\n' "$secs" "$rc"
		printf '        see %s\n' "${ART#"$ROOT"/}/$STAGE_NO-$name.log"
		tail -n "${FAIL_TAIL:-15}" "$ART/$STAGE_NO-$name.log" | sed 's/^/        | /'
		record_stage "$name" FAIL "$secs"
		FAILED_STAGE="$name"
	fi
}

record_stage() {
	STAGE_NAMES+=("$1"); STAGE_STATUS+=("$2"); STAGE_SECS+=("$3")
	printf '%d\t%s\t%s\t%s\n' "$STAGE_NO" "$1" "$2" "$3" >> "$STAGE_LOG"
}

# --- rung parameters -------------------------------------------------------- #
# 3a proves the pipeline on the existing corpus: os_tasks.jsonl is 1.7 KB and
# tokenizes to ~61 tokens, so seq_len*batch_size must stay under that or
# train.py rejects the dataset. Chat quality is Phase 3b's job, not this one.
CORPUS="$ROOT/SLM/datasets/os_tasks.jsonl"
CONFIG="$ROOT/SLM/configs/tiny_10M.yaml"
MAX_STEPS="${MAX_STEPS:-200}"
SEQ_LEN="${SEQ_LEN:-16}"
BATCH_SIZE="${BATCH_SIZE:-2}"

VOCAB="$WORK/vocab.json"
TOKENS="$WORK/tokens.jsonl"
CKPT="$WORK/final.pt"
MODEL_BIN="$WORK/auton-slm.bin"
NEURAL_ISO="$ROOT/kernels/$ARCH/build/auton-neural.iso"
SERIAL_LOG="$ART/serial-neural.log"
TRANSCRIPT_FILE="${TRANSCRIPT_FILE:-$ROOT/tests/transcripts/boot-basics.txt}"

# --- stages ------------------------------------------------------------------ #
# Each stage CALLS an existing entry point. No stage reimplements logic that
# lives in the tool it invokes.

s_train() {
	mkdir -p "$WORK"
	if [ "$SKIP_TRAIN" -eq 1 ]; then
		# A reused checkpoint is legitimate, a missing one is not — never let
		# --skip-train silently proceed to export a stale or absent model.
		local missing=0
		for f in "$VOCAB" "$CKPT"; do
			[ -f "$f" ] || { echo "--skip-train but $f is missing"; missing=1; }
		done
		[ "$missing" -eq 0 ] || return 1
		echo "reusing checkpoint $CKPT ($(date -r "$CKPT" -u +%Y-%m-%dT%H:%M:%SZ))"
		return 0
	fi

	"$PY" "$ROOT/SLM/tools/tokenizer.py" \
		--input "$CORPUS" --output "$VOCAB" --tokenize-to "$TOKENS" || return 1
	"$PY" "$ROOT/SLM/scripts/train.py" \
		--config "$CONFIG" --dataset "$TOKENS" --output "$WORK" \
		--max-steps "$MAX_STEPS" --seq-len "$SEQ_LEN" --batch-size "$BATCH_SIZE"
}

s_export() {
	"$PY" "$ROOT/SLM/scripts/export_auton.py" \
		--checkpoint "$CKPT" --vocab "$VOCAB" --output "$MODEL_BIN" || return 1
	# export_auton.py already writes <output>.manifest.json; keep it with the run.
	[ -f "$MODEL_BIN.manifest.json" ] && cp "$MODEL_BIN.manifest.json" "$ART/"
	return 0
}

s_parity() {
	"$ROOT/kernels/$ARCH/tests/neural_parity.sh" "$MODEL_BIN" "$CKPT" "$VOCAB"
}

s_iso() {
	make -C "$ROOT/kernels/$ARCH" iso-neural MODEL="$MODEL_BIN"
}

s_boot() {
	# The kernel boots to an interactive prompt and never exits, so waiting for
	# QEMU to finish would always burn the whole timeout. Poll for the last boot
	# marker instead and stop as soon as it lands — a timeout then means the
	# boot genuinely did not complete, not that the VM is merely still running.
	: > "$SERIAL_LOG"
	"$QEMU" -cdrom "$NEURAL_ISO" -serial stdio -display none -no-reboot \
		-m "${MEM:-256M}" > "$SERIAL_LOG" 2>/dev/null &
	local qemu_pid=$! booted=0 waited=0
	local limit="${BOOT_TIMEOUT:-90}"

	while [ "$waited" -lt "$limit" ]; do
		if grep -q '\[BOOT\] OK' "$SERIAL_LOG" 2>/dev/null; then booted=1; break; fi
		kill -0 "$qemu_pid" 2>/dev/null || break   # QEMU exited on its own
		sleep 1
		waited=$((waited + 1))
	done

	kill "$qemu_pid" 2>/dev/null
	wait "$qemu_pid" 2>/dev/null || true

	if [ ! -s "$SERIAL_LOG" ]; then
		echo "no serial output captured in ${waited}s"
		return 1
	fi
	if [ "$booted" -ne 1 ]; then
		echo "boot did not reach [BOOT] OK within ${limit}s; last lines:"
		tail -5 "$SERIAL_LOG"
		return 1
	fi
	echo "booted in ${waited}s ($(wc -l < "$SERIAL_LOG" | tr -d ' ') lines of serial output)"
	return 0
}

s_markers() {
	local serial fail=0
	serial="$(cat "$SERIAL_LOG")"
	# A neural boot must satisfy the ordinary boot markers AND the model-loaded
	# /backend-selected chain. Both sets come from acceptance_tests.py.
	for set_name in boot neural; do
		markers_load "$set_name" || return 1
		echo "--- $set_name ---"
		markers_check "$serial"
		[ "$MARKERS_FAILED" -eq 0 ] || fail=1
	done
	return "$fail"
}

s_transcript() {
	# Driven against the rule-engine ISO: these are deterministic system answers,
	# and rung 3a's model is trained only far enough to prove the pipeline, not
	# to hold a conversation. Chat quality is graded in Phase 6.
	local iso="$ROOT/kernels/$ARCH/build/auton.iso"
	[ -f "$iso" ] || make -C "$ROOT/kernels/$ARCH" iso >/dev/null || return 1
	"$ROOT/scripts/transcript.sh" "$TRANSCRIPT_FILE" "$iso" "$ART/serial-transcript.log"
}

echo "AUTON e2e — rung $RUNG$([ "$SKIP_TRAIN" -eq 1 ] && echo ' (train skipped)')"
echo "artifacts: ${ART#"$ROOT"/}"
echo

RUN_START="$(date +%s)"
stage train      s_train
stage export     s_export
stage parity     s_parity
stage iso        s_iso
stage boot       s_boot
stage markers    s_markers
stage transcript s_transcript
RUN_SECS=$(( $(date +%s) - RUN_START ))

# --- verdict ---------------------------------------------------------------- #
echo
if [ -z "$FAILED_STAGE" ]; then
	echo "GREEN  all $TOTAL_STAGES stages passed in ${RUN_SECS}s"
	VERDICT=GREEN
else
	echo "RED    stage '$FAILED_STAGE' failed after ${RUN_SECS}s"
	VERDICT=RED
fi
echo "artifacts: ${ART#"$ROOT"/}"

[ "$VERDICT" = GREEN ]
