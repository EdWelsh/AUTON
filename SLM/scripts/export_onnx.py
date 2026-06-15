#!/usr/bin/env python3
"""Export an AUTON SLM checkpoint to ONNX.

Wraps the model so it emits logits only (the training tuple drops the loss),
traces it with a dummy ``input_ids`` batch, writes the ONNX graph, and validates
it with ``onnx.checker``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the SLM package root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _build_logits_wrapper(model):
    """Wrap a model so ``forward(input_ids) -> logits`` (drops the loss tuple)."""
    import torch.nn as nn

    class _LogitsOnly(nn.Module):
        def __init__(self, inner: nn.Module) -> None:
            super().__init__()
            self.inner = inner

        def forward(self, input_ids):
            logits, _ = self.inner(input_ids)
            return logits

    return _LogitsOnly(model).eval()


def export_onnx(model_path: str, output_path: str, seq_len: int = 16) -> dict:
    import torch

    from model.checkpoint import load_checkpoint

    model, _ = load_checkpoint(model_path, "cpu")
    wrapper = _build_logits_wrapper(model)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.randint(0, model.cfg.vocab_size, (1, seq_len), dtype=torch.long)

    torch.onnx.export(
        wrapper,
        (dummy,),
        str(out),
        input_names=["input_ids"],
        output_names=["logits"],
        dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "logits": {0: "batch", 1: "seq"}},
        opset_version=17,
        dynamo=False,
    )

    import onnx

    onnx.checker.check_model(str(out))
    return {"output": str(out), "size_bytes": out.stat().st_size, "valid": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export model to ONNX")
    parser.add_argument("--model", required=True, help="Model path")
    parser.add_argument("--output", required=True, help="Output ONNX path")
    args = parser.parse_args(argv)

    summary = export_onnx(args.model, args.output)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
