#!/usr/bin/env python3
"""Quantize an AUTON SLM checkpoint to INT8/INT4 weights.

Uses portable symmetric per-tensor quantization of the 2D weight matrices
(CPU-only, no CUDA/bitsandbytes dependency): each weight ``W`` is stored as
``round(W / scale)`` in the target bit range plus a per-tensor ``scale``. The
output is a self-describing payload that dequantizes back to the original shape.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Make the SLM package root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if TYPE_CHECKING:  # torch is imported lazily inside functions (heavy dependency)
    import torch

def quantize_tensor(weight: "torch.Tensor", bits: int) -> tuple["torch.Tensor", float]:
    """Symmetric per-tensor quantization. Returns ``(int8_codes, scale)``."""
    import torch

    qmax = (1 << (bits - 1)) - 1  # 127 for int8, 7 for int4
    amax = weight.abs().max().item()
    scale = (amax / qmax) if amax > 0 else 1.0
    codes = torch.clamp(torch.round(weight / scale), -qmax - 1, qmax).to(torch.int8)
    return codes, scale


def quantize_state(state: dict, bits: int) -> tuple[dict, dict]:
    """Quantize all 2D float weights; pass other tensors through unchanged.

    Returns ``(quantized_payload, stats)``.
    """
    q: dict[str, dict] = {}
    passthrough: dict[str, torch.Tensor] = {}
    quantized_params = 0
    total_params = 0
    for name, tensor in state.items():
        total_params += tensor.numel()
        if tensor.dim() == 2 and tensor.is_floating_point():
            codes, scale = quantize_tensor(tensor, bits)
            q[name] = {"codes": codes, "scale": scale, "shape": list(tensor.shape)}
            quantized_params += tensor.numel()
        else:
            passthrough[name] = tensor
    stats = {
        "bits": bits,
        "quantized_params": quantized_params,
        "passthrough_params": total_params - quantized_params,
        "total_params": total_params,
        "compression_ratio": round(32 / bits, 2),
    }
    return {"quantized": q, "passthrough": passthrough}, stats


def quantize_checkpoint(checkpoint_path: str, output_path: str, bits: int) -> dict:
    import torch

    payload = torch.load(Path(checkpoint_path), map_location="cpu", weights_only=False)
    state = payload["model"]
    qpayload, stats = quantize_state(state, bits)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {"config": payload.get("config"), "bits": bits, **qpayload},
        out,
    )
    stats["output"] = str(out)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Quantize SLM model")
    parser.add_argument("--checkpoint", required=True, help="Model checkpoint path")
    parser.add_argument("--bits", type=int, default=4, choices=[4, 8], help="Quantization bits")
    parser.add_argument("--output", required=True, help="Output path")
    args = parser.parse_args(argv)

    stats = quantize_checkpoint(args.checkpoint, args.output, args.bits)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
