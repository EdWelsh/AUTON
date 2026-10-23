#!/usr/bin/env bash
# Run the remaining repairs one after another (one subscription, one local model slot).
#   scripts/repair-queue.sh r11-conformance r9-aarch64 r10-f00f r12-doom
# A hint file .artifacts/repair/hints/<run>-1.txt is used when present.
cd "$(dirname "$0")/.." || exit 1
for run in "$@"; do
	hint=".artifacts/repair/hints/${run}-1.txt"
	args=("$run"); [ -f "$hint" ] && args+=(--hint "$hint")
	echo "$(date -u +%FT%TZ) repair queue: $run"
	.venv/bin/python scripts/repair_run.py "${args[@]}"
done
echo "$(date -u +%FT%TZ) repair queue: done"
