#!/usr/bin/env python3
"""Export an AUTON SLM checkpoint to GGUF.

Writes a real GGUF container (``GGUF`` magic) with architecture metadata and the
model's float32 tensors using the ``gguf`` writer. The result is loadable by
``tools/gguf_validator`` and standard GGUF tooling.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the SLM package root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def export_gguf(model_path: str, output_path: str) -> dict:
    import numpy as np
    import torch
    from gguf import GGUFWriter

    from model.config import ModelConfig

    payload = torch.load(Path(model_path), map_location="cpu", weights_only=False)
    cfg = ModelConfig.from_dict(payload["config"])
    state = payload["model"]

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    writer = GGUFWriter(str(out), arch="auton-slm")
    writer.add_uint32("auton-slm.embedding_length", cfg.hidden_size)
    writer.add_uint32("auton-slm.block_count", cfg.num_layers)
    writer.add_uint32("auton-slm.attention.head_count", cfg.num_attention_heads)
    writer.add_uint32("auton-slm.attention.head_count_kv", cfg.num_key_value_heads)
    writer.add_uint32("auton-slm.feed_forward_length", cfg.intermediate_size)
    writer.add_uint32("auton-slm.vocab_size", cfg.vocab_size)
    writer.add_uint32("auton-slm.context_length", cfg.max_position_embeddings)

    n_tensors = 0
    for name, tensor in state.items():
        arr = tensor.detach().to(torch.float32).cpu().numpy().astype(np.float32)
        writer.add_tensor(name, arr)
        n_tensors += 1

    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()

    return {"output": str(out), "tensors": n_tensors, "size_bytes": out.stat().st_size}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export model to GGUF")
    parser.add_argument("--model", required=True, help="Model path")
    parser.add_argument("--output", required=True, help="Output GGUF path")
    args = parser.parse_args(argv)

    summary = export_gguf(args.model, args.output)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
