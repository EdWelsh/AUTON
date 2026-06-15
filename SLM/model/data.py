"""Tokenized-dataset loading and fixed-length batching for training/eval.

Consumes the JSONL shape produced by ``tools/tokenizer.tokenize_dataset``:
each line is ``{"ids": [int, ...]}``. Sequences are concatenated into one token
stream and chunked into ``seq_len``-sized training windows.
"""

from __future__ import annotations

import json
from pathlib import Path

import torch


def load_token_stream(path: str | Path) -> list[int]:
    """Read a tokenized JSONL file into a flat list of token IDs.

    Returns an empty list if the file is missing or unreadable.
    """
    p = Path(path)
    if not p.exists():
        return []
    ids: list[int] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("ids"), list):
            ids.extend(int(t) for t in obj["ids"])
    return ids


def make_batches(
    token_ids: list[int],
    seq_len: int,
    batch_size: int,
    device: str = "cpu",
):
    """Yield ``(input_ids, labels)`` tensors of shape ``(batch_size, seq_len)``.

    The stream is chunked into non-overlapping ``seq_len`` windows; ``labels`` is
    the same window (next-token loss shifts internally in the model). Drops a
    trailing partial batch. Yields nothing if there is not even one full window.
    """
    n_windows = len(token_ids) // seq_len
    if n_windows == 0:
        return
    windows = [
        token_ids[i * seq_len : (i + 1) * seq_len] for i in range(n_windows)
    ]
    for start in range(0, len(windows) - batch_size + 1, batch_size):
        chunk = windows[start : start + batch_size]
        batch = torch.tensor(chunk, dtype=torch.long, device=device)
        yield batch, batch
