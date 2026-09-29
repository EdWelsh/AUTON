#!/usr/bin/env bash
# Run the kernel-writing agent loop natively, against the local model.
#
# Usage: scripts/orchestrate-native.sh "<goal>" [--timeout SECS]
#
# The native equivalent of `docker compose run orchestrate`. Caps come from
# [orchestrator].max_iterations and [llm.cost] in agent/config/auton.toml —
# keep them tight for a local model.
#
# SECURITY: agent tool arguments are executed as argv, never as a shell string,
# and the `shell` tool is confined to an allowlist (base_agent.py). Injection
# through a task title or a test name is closed and held closed by
# tests/unit/agents/test_base_agent_injection.py. What is NOT bounded is what
# an allowlisted program can be told to do — `git` and `make` can still reach
# outside the workspace — so a goal drawn from untrusted text still warrants
# a sandbox.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"   # validators shell out to the cross toolchain
PY="${PYTHON:-$ROOT/.venv/bin/python}"
case "$PY" in /*) ;; *) PY="$ROOT/$PY";; esac

USAGE='usage: orchestrate-native.sh "<goal>" [--timeout SECS] [--subject DIR] | --resume [--timeout SECS]'
GOAL=""
RESUME=""
SUBJECT=""
TIMEOUT="${ORCH_TIMEOUT:-900}"
# At the budget the orchestrator gets TERM and this long to commit its work in
# flight and save its graph before KILL (w17: R1 lost an uncommitted pmm.c).
GRACE="${ORCH_GRACE:-120}"
while [ $# -gt 0 ]; do
	case "$1" in
		--timeout) TIMEOUT="${2:?--timeout needs a value}"; shift 2 ;;
		--resume) RESUME=1; shift ;;
		--subject) SUBJECT="$(cd "${2:?--subject needs a directory}" && pwd)" || exit 2; shift 2 ;;
		-*) echo "unknown argument: $1" >&2; echo "$USAGE" >&2; exit 2 ;;
		*) [ -z "$GOAL" ] || { echo "$USAGE" >&2; exit 2; }; GOAL="$1"; shift ;;
	esac
done
[ -n "$GOAL" ] || [ -n "$RESUME" ] || { echo "$USAGE" >&2; exit 2; }
RUN_ARGS=(run)
[ -n "$GOAL" ] && RUN_ARGS+=("$GOAL")
[ -n "$RESUME" ] && RUN_ARGS+=(--resume)
[ -n "$SUBJECT" ] && RUN_ARGS+=(--subject "$SUBJECT")

LOG="${ORCH_LOG:-$ROOT/.artifacts/orchestrator/$(date -u +%Y-%m-%dT%H-%M-%SZ).log}"
# ORCH_CONFIG selects another config (an experiment's workspace and caps) without
# editing the repo's own.
CONFIG="${ORCH_CONFIG:-$ROOT/agent/config/auton.toml}"
mkdir -p "$(dirname "$LOG")"

echo "goal:    ${GOAL:-(resuming the saved run)}"
echo "model:   $("$PY" -c "
import tomllib; print(tomllib.load(open('$CONFIG','rb'))['llm']['model'])" 2>/dev/null || echo unknown)"
echo "cap:     $("$PY" -c "
import tomllib
c=tomllib.load(open('$CONFIG','rb'))
print(c.get('orchestrator',{}).get('max_iterations',50), 'iterations')" 2>/dev/null || echo '?')"
echo "log:     ${LOG#"$ROOT"/}"
echo

cd "$ROOT/agent" || exit 1
# Plain output: the rich console emits ANSI and hyperlink escapes that make the
# captured log hard to grep for the phase transitions this lane measures.
TERM=dumb NO_COLOR=1 AUTON_KILL_AFTER="$GRACE" auton_timeout "$TIMEOUT" "$PY" \
	-m orchestrator.cli --config "$CONFIG" "${RUN_ARGS[@]}" 2>&1 | tee "$LOG"
rc="${PIPESTATUS[0]}"

echo
# The log decides, not the status: at the budget `timeout` reports 124 whether
# the orchestrator paused cleanly inside the grace period or was killed.
if grep -q "Refusing to resume" "$LOG"; then
	echo "ORCHESTRATOR: RESUME REFUSED (see the reason above)"
	exit 2
fi
if grep -q "Orchestration paused" "$LOG"; then
	echo "ORCHESTRATOR: PAUSED after ${TIMEOUT}s — work in flight committed, graph saved"
	echo "  resume: ORCH_CONFIG=$CONFIG scripts/orchestrate-native.sh --resume"
	exit 75
fi
if [ "$rc" -eq 124 ]; then
	echo "ORCHESTRATOR: TIMEOUT after ${TIMEOUT}s, not paused within the ${GRACE}s grace"
	echo "  (killed: work in flight may be uncommitted; --resume may still work from the last iteration)"
	exit 1
fi

# A terminal phase is the bar for Task 1 — success or a recorded failure both
# count; hanging does not.
if grep -qE "Orchestration completed successfully|Orchestration failed" "$LOG"; then
	echo "ORCHESTRATOR: reached a terminal phase (rc=$rc)"
	exit 0
fi
echo "ORCHESTRATOR: no terminal phase reported (rc=$rc)"
exit 1
