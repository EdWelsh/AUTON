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

# --- stages (bodies land in Task 3) ----------------------------------------- #
s_train()      { echo "train: not yet wired"; }
s_export()     { echo "export: not yet wired"; }
s_parity()     { echo "parity: not yet wired"; }
s_iso()        { echo "iso: not yet wired"; }
s_boot()       { echo "boot: not yet wired"; }
s_markers()    { echo "markers: not yet wired"; }
s_transcript() { echo "transcript: not yet wired"; }

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
