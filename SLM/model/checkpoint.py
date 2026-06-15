"""Checkpoint save/load helpers shared by train/evaluate/quantize/export.

A checkpoint is a single ``torch.save`` payload:
    {"model": state_dict, "config": ModelConfig.to_dict(), "step": int, "meta": {...}}
"""

from __future__ import annotations

from pathlib import Path

import torch

from model.config import ModelConfig
from model.transformer import SLMTransformer


def save_checkpoint(
    model: SLMTransformer,
    path: str | Path,
    step: int = 0,
    meta: dict | None = None,
) -> Path:
    """Write a checkpoint to ``path`` (parent dirs created) and return it."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model.state_dict(),
        "config": model.cfg.to_dict(),
        "step": step,
        "meta": meta or {},
    }
    torch.save(payload, out)
    return out


def load_checkpoint(path: str | Path, device: str = "cpu") -> tuple[SLMTransformer, dict]:
    """Rebuild an :class:`SLMTransformer` from a checkpoint, returning the payload too."""
    payload = torch.load(Path(path), map_location=device, weights_only=False)
    cfg = ModelConfig.from_dict(payload["config"])
    model = SLMTransformer(cfg).to(device)
    model.load_state_dict(payload["model"])
    model.eval()
    return model, payload
