#!/usr/bin/env python3
"""Train the AUTON SLM (decoder-only transformer) on a tokenized dataset.

Loads a YAML model config, builds the model, streams a tokenized JSONL dataset
(``{"ids": [...]}`` per line), and runs an AdamW training loop with cosine decay
and linear warmup, checkpointing periodically. Designed to run end-to-end on the
tiny config on CPU in seconds.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

# Make the SLM package root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def lr_at_step(step: int, base_lr: float, warmup: int, total: int) -> float:
    """Linear warmup then cosine decay to 10% of ``base_lr``."""
    if warmup > 0 and step < warmup:
        return base_lr * (step + 1) / warmup
    progress = min(1.0, (step - warmup) / max(1, total - warmup))
    return base_lr * (0.1 + 0.9 * 0.5 * (1.0 + math.cos(math.pi * progress)))


def train(
    config_path: str,
    dataset_path: str,
    output_dir: str,
    max_steps: int,
    seq_len: int = 64,
    batch_size: int | None = None,
    device: str = "cpu",
) -> dict:
    """Run training; return a summary dict. Raises ValueError on insufficient data."""
    import torch

    from model.checkpoint import save_checkpoint
    from model.config import load_config
    from model.data import load_token_stream, make_batches
    from model.transformer import SLMTransformer

    model_cfg, train_cfg = load_config(config_path)
    bsz = batch_size or train_cfg.batch_size

    tokens = load_token_stream(dataset_path)
    # Clamp ids into the model's vocab range so an arbitrary tokenizer can't OOB.
    tokens = [t % model_cfg.vocab_size for t in tokens]
    if len(tokens) < seq_len * bsz:
        raise ValueError(
            f"dataset too small: need >= {seq_len * bsz} tokens for one batch, "
            f"got {len(tokens)} (try a smaller --seq-len/--batch-size or more data)"
        )

    torch.manual_seed(0)
    model = SLMTransformer(model_cfg).to(device)
    model.train()
    opt = torch.optim.AdamW(
        model.parameters(),
        lr=train_cfg.learning_rate,
        weight_decay=train_cfg.weight_decay,
        betas=(0.9, 0.95),
    )

    out = Path(output_dir)
    step = 0
    last_loss = float("nan")
    done = False
    while not done:
        for input_ids, labels in make_batches(tokens, seq_len, bsz, device):
            lr = lr_at_step(step, train_cfg.learning_rate, train_cfg.warmup_steps, max_steps)
            for group in opt.param_groups:
                group["lr"] = lr

            _, loss = model(input_ids, labels)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()

            last_loss = float(loss.item())
            step += 1
            if step % max(1, train_cfg.checkpoint_every) == 0:
                save_checkpoint(model, out / f"step_{step}.pt", step, {"loss": last_loss})
            if step >= max_steps:
                done = True
                break
        else:
            continue  # dataset exhausted before max_steps; iterate again

    final_ckpt = save_checkpoint(model, out / "final.pt", step, {"loss": last_loss})
    return {
        "steps": step,
        "final_loss": last_loss,
        "perplexity": math.exp(last_loss) if last_loss == last_loss else None,
        "parameters": model.num_parameters(),
        "checkpoint": str(final_ckpt),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train SLM model")
    parser.add_argument("--config", required=True, help="Model config YAML")
    parser.add_argument("--dataset", required=True, help="Tokenized dataset path (JSONL)")
    parser.add_argument("--output", default="SLM/models/checkpoints", help="Output directory")
    parser.add_argument("--max-steps", type=int, default=10000, help="Max training steps")
    parser.add_argument("--seq-len", type=int, default=64, help="Training sequence length")
    parser.add_argument("--batch-size", type=int, default=None, help="Override config batch size")
    parser.add_argument("--device", default="cpu", help="torch device (cpu/cuda/mps)")
    args = parser.parse_args(argv)

    summary = train(
        args.config,
        args.dataset,
        args.output,
        args.max_steps,
        seq_len=args.seq_len,
        batch_size=args.batch_size,
        device=args.device,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
