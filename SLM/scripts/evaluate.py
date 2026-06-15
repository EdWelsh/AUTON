#!/usr/bin/env python3
"""Evaluate an AUTON SLM checkpoint: mean cross-entropy loss and perplexity.

Loads a checkpoint, streams a tokenized JSONL dataset, and reports the average
next-token loss and perplexity (``exp(loss)``) over all full windows.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the SLM package root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def evaluate(
    checkpoint_path: str,
    dataset_path: str,
    seq_len: int = 64,
    batch_size: int = 8,
    device: str = "cpu",
) -> dict:
    """Return ``{loss, perplexity, windows, tokens}``. Raises ValueError if no data."""
    import torch

    from model.checkpoint import load_checkpoint
    from model.data import load_token_stream, make_batches
    from tools.metrics import compute_perplexity

    model, _ = load_checkpoint(checkpoint_path, device)
    tokens = load_token_stream(dataset_path)
    tokens = [t % model.cfg.vocab_size for t in tokens]
    if len(tokens) < seq_len * batch_size:
        raise ValueError(
            f"dataset too small to evaluate: need >= {seq_len * batch_size} tokens, "
            f"got {len(tokens)}"
        )

    total_loss = 0.0
    n_batches = 0
    with torch.no_grad():
        for input_ids, labels in make_batches(tokens, seq_len, batch_size, device):
            _, loss = model(input_ids, labels)
            total_loss += float(loss.item())
            n_batches += 1

    mean_loss = total_loss / max(1, n_batches)
    return {
        "loss": mean_loss,
        "perplexity": compute_perplexity(mean_loss),
        "windows": n_batches * batch_size,
        "tokens": len(tokens),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate SLM model")
    parser.add_argument("--checkpoint", required=True, help="Model checkpoint path")
    parser.add_argument("--dataset", required=True, help="Test dataset path (tokenized JSONL)")
    parser.add_argument("--seq-len", type=int, default=64, help="Evaluation sequence length")
    parser.add_argument("--batch-size", type=int, default=8, help="Evaluation batch size")
    parser.add_argument("--device", default="cpu", help="torch device (cpu/cuda/mps)")
    args = parser.parse_args(argv)

    summary = evaluate(
        args.checkpoint,
        args.dataset,
        seq_len=args.seq_len,
        batch_size=args.batch_size,
        device=args.device,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
