"""Model evaluation metrics."""

import math


def compute_perplexity(loss: float) -> float:
    """Compute perplexity from loss."""
    return math.exp(loss)


def compute_accuracy(predictions, labels) -> float:
    """Compute accuracy."""
    # TODO: Implement accuracy computation
    return 0.0
