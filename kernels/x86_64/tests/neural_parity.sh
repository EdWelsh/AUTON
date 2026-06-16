#!/usr/bin/env bash
# Validate the in-kernel neural forward pass against the PyTorch reference:
# build the host harness, generate greedily from a few prompts, and diff the
# token sequences against torch run on the same checkpoint.
#
# Usage: tests/neural_parity.sh <model.bin> <checkpoint.pt> <vocab.json>
# Requires: clang, a Python env with torch + the SLM package importable.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
MODEL="${1:?model.bin}"
CKPT="${2:?checkpoint.pt}"
VOCAB="${3:?vocab.json}"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
case "$PY" in /*) ;; *) PY="$ROOT/$PY";; esac     # absolutize before cd

cd "$(dirname "$0")/.."
clang -O2 -Ikernel/include kernel/slm/neural/neural_backend.c kernel/lib/kmath.c \
	tests/neural_forward_host.c -lm -o /tmp/neural_forward_host || exit 1

PROMPTS=("2 4 5" "2 29 30" "2 4")
fail=0
for p in "${PROMPTS[@]}"; do
	kern=$(/tmp/neural_forward_host "$MODEL" $p | sed 's/^gen: //')
	ref=$(CKPT="$CKPT" VOCAB="$VOCAB" PROMPT="$p" SLMROOT="$ROOT/SLM" "$PY" - <<'PYEOF'
import os, sys
sys.path.insert(0, os.environ["SLMROOT"])
import torch
from model.checkpoint import load_checkpoint
m, _ = load_checkpoint(os.environ["CKPT"])
ids = [int(x) for x in os.environ["PROMPT"].split()]
out, cur = [], list(ids)
for _ in range(12):
    with torch.no_grad():
        lg, _ = m(torch.tensor([cur]))
    nt = int(lg[0, -1].argmax())
    if nt in (0, 3):
        break
    out.append(nt); cur.append(nt)
print(" ".join(str(x) for x in out))
PYEOF
)
	if [ "$kern" = "$ref" ]; then
		echo "PASS [$p] -> $kern"
	else
		echo "FAIL [$p] kernel='$kern' torch='$ref'"
		fail=1
	fi
done
[ "$fail" -eq 0 ] && echo "NEURAL PARITY: ALL PASS"
exit "$fail"
