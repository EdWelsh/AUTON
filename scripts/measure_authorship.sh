#!/usr/bin/env bash
# Authorship cost, counted one way for controls and experiments alike.
#   scripts/measure_authorship.sh --service dhcp
#   scripts/measure_authorship.sh --driver virtio-console --root <workspace>
# The rules are in agent/tools/measure_authorship.py; this only finds Python.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
exec "$PY" "$ROOT/agent/tools/measure_authorship.py" "$@"
