#!/usr/bin/env bash
# Operator E2E lane: "speak a goal, AUTON does the steps", verified on this host.
#
# Usage: scripts/operator-e2e.sh
#
# Runs the Excel scenario on BOTH paths — the deterministic planner (no model
# needed, the regression floor) and the live brain — and proves the approval
# gate actually blocks irreversible actions.
#
# The live path is driven with --brain llm, never auto: auto falls back to the
# rule engine on failure, so a broken model would look identical to a working
# one. TaskResult.brain is the only proof of which path ran.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
case "$PY" in /*) ;; *) PY="$ROOT/$PY";; esac

fail=0
run() {
	local desc="$1"; shift
	if "$@" >/dev/null 2>&1; then
		echo "PASS  $desc"
	else
		echo "FAIL  $desc"
		fail=1
	fi
}

echo "----- operator lane -----"

run "excel scenario, both paths + approval gate" \
	"$PY" -m pytest "$ROOT/controlplane/tests/test_operator.py" -q

run "approval defaults and workspace containment" \
	"$PY" -m pytest "$ROOT/controlplane/tests/test_operator.py" \
	-q -k "TestApprovalDefaults or TestWorkspaceContainment"

run "brain provenance (rule path reports rule)" \
	"$PY" -m pytest "$ROOT/controlplane/tests/test_operator.py" \
	-q -k "TestBrainProvenance"

# The live-brain test skips itself when Ollama is unreachable. A skipped live
# path must not read as a verified one, so report which happened.
echo "----- environment -----"
if "$PY" -c "import httpx,sys; httpx.get('http://localhost:11434/api/tags',timeout=2).raise_for_status()" \
	>/dev/null 2>&1; then
	MODEL="$(cd "$ROOT/agent" 2>/dev/null && "$PY" -c "
import tomllib
print(tomllib.load(open('config/auton.toml','rb'))['llm']['model'])" 2>/dev/null || echo unknown)"
	echo "  ollama: reachable (live-brain path exercised, model $MODEL)"
else
	echo "  ollama: UNREACHABLE — live-brain path SKIPPED, only the rule path is verified"
fi
echo "-------------------------"

if [ "$fail" -eq 0 ]; then
	echo "OPERATOR: ALL PASS"
else
	echo "OPERATOR: FAILURES"
	exit 1
fi
