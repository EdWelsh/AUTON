#!/usr/bin/env python3
"""Export a trained checkpoint to the AUTON flat format the kernel loads.

Reads a checkpoint (``model/checkpoint.py`` payload), emits weights in the fixed
tensor order defined by ``tools/auton_format.py``, appends the tokenizer vocab,
and writes a JSON manifest (dims + sha256) alongside.

The kernel tokenizer is word-level (whitespace split) to match
``tools/tokenizer.py``; the exported vocab is the id->token table.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.auton_format import FlatHeader, QUANT_FP32, validate, write_model  # noqa: E402


def _layer_tensors(state: dict, i: int) -> list:
    """Per-layer tensors in the documented order (each as a flat float list)."""
    p = f"layers.{i}."
    return [
        state[p + "attn_norm.weight"],
        state[p + "attn.q_proj.weight"],
        state[p + "attn.k_proj.weight"],
        state[p + "attn.v_proj.weight"],
        state[p + "attn.o_proj.weight"],
        state[p + "ffn_norm.weight"],
        state[p + "ffn.gate_proj.weight"],
        state[p + "ffn.down_proj.weight"],
        state[p + "ffn.up_proj.weight"],
    ]


def export(checkpoint: str, vocab_path: str, output: str) -> dict:
    """Write the flat model + manifest. Returns the manifest dict."""
    import torch

    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    cfg = payload["config"]
    state = payload["model"]

    header = FlatHeader(
        dim=cfg["hidden_size"],
        hidden_dim=cfg["intermediate_size"],
        n_layers=cfg["num_layers"],
        n_heads=cfg["num_attention_heads"],
        n_kv_heads=cfg["num_key_value_heads"],
        vocab_size=cfg["vocab_size"],
        seq_len=cfg["max_position_embeddings"],
        quant=QUANT_FP32,
    )

    # Weights, in the exact order tools/auton_format.py documents.
    tensors = [state["embed_tokens.weight"]]
    # Group all per-layer tensors of the same kind is NOT required; the kernel
    # reads them interleaved per layer in this order.
    for i in range(header.n_layers):
        tensors.extend(_layer_tensors(state, i))
    tensors.append(state["norm.weight"])

    weights: list[float] = []
    for t in tensors:
        weights.extend(t.detach().to(torch.float32).flatten().tolist())

    # Vocab: id -> token string (word-level). Pad to vocab_size with empties.
    vocab_map = json.loads(Path(vocab_path).read_text(encoding="utf-8"))
    id_to_tok = {v: k for k, v in vocab_map.items()}
    vocab: list[tuple[float, bytes]] = []
    for tid in range(header.vocab_size):
        tok = id_to_tok.get(tid, "")
        vocab.append((float(-tid), tok.encode("utf-8")))

    size = write_model(output, header, weights, vocab)
    validate(output)  # fail loudly if the layout is inconsistent

    sha = hashlib.sha256(Path(output).read_bytes()).hexdigest()
    manifest = {
        "format": "auton-flat-v1",
        "file": Path(output).name,
        "bytes": size,
        "sha256": sha,
        "arch": {
            "dim": header.dim,
            "hidden_dim": header.hidden_dim,
            "n_layers": header.n_layers,
            "n_heads": header.n_heads,
            "n_kv_heads": header.n_kv_heads,
            "vocab_size": header.vocab_size,
            "seq_len": header.seq_len,
            "quant": "fp32",
        },
    }
    Path(output + ".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export SLM to AUTON flat format")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--vocab", required=True, help="tokenizer vocab JSON")
    parser.add_argument("--output", default="SLM/models/exports/auton-slm.bin")
    args = parser.parse_args(argv)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    manifest = export(args.checkpoint, args.vocab, args.output)
    print(f"wrote {args.output} ({manifest['bytes']} bytes) sha256={manifest['sha256'][:16]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
