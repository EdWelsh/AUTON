"""Model evaluation metrics."""

from __future__ import annotations

import math
from collections.abc import Sequence


def compute_perplexity(loss: float) -> float:
    """Compute perplexity from a cross-entropy loss: ppl = exp(loss)."""
    return math.exp(loss)


def compute_accuracy(predictions: Sequence, labels: Sequence) -> float:
    """Compute prediction accuracy in [0.0, 1.0].

    Returns the fraction of positions where prediction == label over the
    overlapping length. Returns 0.0 for empty input or a length mismatch with
    no overlap.
    """
    n = min(len(predictions), len(labels))
    if n == 0:
        return 0.0
    correct = sum(1 for pred, label in zip(predictions, labels) if pred == label)
    return correct / n
