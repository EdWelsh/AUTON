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
# The model/checkpoint/vocab need the same treatment: this script cds below, so
# a relative path passed by the caller silently stops resolving. Both sides then
# fail to load anything, both print nothing, and "" = "" reported ALL PASS.
for _v in MODEL CKPT VOCAB; do
	case "${!_v}" in
		/*) ;;
		*)  printf -v "$_v" '%s' "$PWD/${!_v}" ;;
	esac
done
for _v in MODEL CKPT VOCAB; do
	[ -f "${!_v}" ] || { echo "FAIL $_v not found: ${!_v}" >&2; exit 2; }
done

# Read the model's quant mode from its header so the reference matches it.
QUANT_MODE="$("$PY" - "$MODEL" <<'PYEOF'
import struct, sys
with open(sys.argv[1], "rb") as f:
    head = f.read(48)
# quant is the 10th uint32 after magic/version (see SLM/tools/auton_format.py).
print("int8" if struct.unpack_from("<I", head, 36)[0] == 1 else "fp32")
PYEOF
)"
echo "parity mode: $QUANT_MODE"

cd "$(dirname "$0")/.."
clang -O2 -Ikernel/include kernel/slm/neural/neural_backend.c kernel/lib/kmath.c \
	tests/neural_forward_host.c -lm -o /tmp/neural_forward_host || exit 1

# Real questions in v2 vocabulary, each ending at <sep> — the exact shape the
# kernel builds. Regenerated when the tokenizer changed; the old ids addressed
# different words entirely.
#   "what is pci 8086:100e"          -> 2 27 9 71 66 4
#   "can you run a database server"  -> 2 39 43 11 5 172 14 4
#   "what is my ip"                  -> 2 27 9 110 231 4
PROMPTS=("2 27 9 71 66 4" "2 39 43 11 5 172 14 4" "2 27 9 110 231 4")
fail=0
for p in "${PROMPTS[@]}"; do
	kern=$(/tmp/neural_forward_host "$MODEL" $p | sed 's/^gen: //')
	ref=$(CKPT="$CKPT" VOCAB="$VOCAB" PROMPT="$p" SLMROOT="$ROOT/SLM" \
	      QUANT="$QUANT_MODE" "$PY" - <<'PYEOF'
import os, sys
sys.path.insert(0, os.environ["SLMROOT"])
import torch
from model.checkpoint import load_checkpoint
m, _ = load_checkpoint(os.environ["CKPT"])

if os.environ.get("QUANT") == "int8":
    # Compare int8 kernel against an int8 reference, not the fp32 one. Both
    # sides then do the same arithmetic on the same weights, so rounding is
    # common to both and any divergence left is an implementation bug — which
    # is the only thing parity has ever been able to detect. Criterion fixed
    # before measuring; see the rung-3c parity criterion note.
    with torch.no_grad():
        for mod in m.modules():
            w = getattr(mod, "weight", None)
            if w is not None and w.dim() == 2 and w.is_floating_point():
                amax = w.abs().max().item()
                scale = (amax / 127.0) if amax > 0 else 1.0
                w.copy_(torch.clamp(torch.round(w / scale), -128, 127) * scale)
ids = [int(x) for x in os.environ["PROMPT"].split()]
out, cur = [], list(ids)
for _ in range(12):
    with torch.no_grad():
        lg, _ = m(torch.tensor([cur]))
    nt = int(lg[0, -1].argmax())
    # Match the kernel: stop at <pad>, <eos> and <sep>. <sep> is prompt
    # grammar, so emitting it means a new question has started.
    if nt in (0, 3, 4):
        break
    out.append(nt); cur.append(nt)
print(" ".join(str(x) for x in out))
PYEOF
)
	# Empty output means neither side generated anything — a load failure, not
	# agreement. Comparing "" to "" must never read as parity.
	if [ -z "$kern" ] || [ -z "$ref" ]; then
		echo "FAIL [$p] no tokens generated (kernel='$kern' torch='$ref')"
		fail=1
	elif [ "$kern" = "$ref" ]; then
		echo "PASS [$p] -> $kern"
	else
		echo "FAIL [$p] kernel='$kern' torch='$ref'"
		fail=1
	fi
done
[ "$fail" -eq 0 ] && echo "NEURAL PARITY: ALL PASS"
exit "$fail"
