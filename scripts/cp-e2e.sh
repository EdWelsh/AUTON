#!/usr/bin/env bash
# Control-plane E2E lane: the host half of the chat OS, end to end.
#
# Usage: scripts/cp-e2e.sh
#
# Drives one session across terminal/UI/desktop, then asserts every backend
# either does the real thing or refuses with a reason. Needs no VM.
#
# A missing tool is a CASE, not a blocked run: with Docker stopped the docker
# backend must say so, and that is a pass. The lane fails on an exception, a
# silent empty answer, or a false claim of success.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
case "$PY" in /*) ;; *) PY="$ROOT/$PY";; esac

fail=0
check() {
	if "$@" >/dev/null 2>&1; then
		echo "PASS  $DESC"
	else
		echo "FAIL  $DESC"
		fail=1
	fi
}

echo "----- control-plane lane -----"

DESC="cross-surface + backend honesty suite"
check "$PY" -m pytest "$ROOT/controlplane/tests/test_e2e_surfaces.py" -q

DESC="session continuity"
check "$PY" -m pytest "$ROOT/controlplane/tests/test_session_continuity.py" -q

DESC="full control-plane suite"
check "$PY" -m pytest "$ROOT/controlplane/tests" -q

# Report the environment the lane ran against, so a green run is interpretable:
# "all backends honest" means something different with Docker up than down.
echo "----- environment -----"
if command -v docker >/dev/null 2>&1; then
	if docker info >/dev/null 2>&1; then
		echo "  docker: daemon up (real container operations exercised)"
	else
		echo "  docker: CLI present, daemon down (honest-refusal path exercised)"
	fi
else
	echo "  docker: CLI absent"
fi
command -v kubectl >/dev/null 2>&1 && echo "  kubectl: present" || echo "  kubectl: absent"
[ -n "${DISPLAY:-}" ] && echo "  display: set" || echo "  display: unset (desktop guarded)"
echo "------------------------------"

if [ "$fail" -eq 0 ]; then
	echo "CONTROL PLANE: ALL PASS"
else
	echo "CONTROL PLANE: FAILURES"
	exit 1
fi
