"""Unit tests for SLM.tools.metrics module."""

import math
import sys
from pathlib import Path

# Ensure the SLM package root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.metrics import compute_perplexity, compute_accuracy


class TestComputePerplexity:
    """Tests for the compute_perplexity function."""

    def test_zero_loss(self):
        """Perplexity at loss=0 should be exp(0) = 1.0."""
        assert compute_perplexity(0.0) == 1.0

    def test_loss_one(self):
        """Perplexity at loss=1 should be approximately e."""
        assert abs(compute_perplexity(1.0) - math.e) < 0.01

    def test_monotonically_increasing(self):
        """Perplexity should increase as loss increases."""
        assert compute_perplexity(2.0) > compute_perplexity(1.0)
        assert compute_perplexity(5.0) > compute_perplexity(3.0)

    def test_known_value_loss_3(self):
        """Perplexity at loss=3.0 should be approximately exp(3.0)."""
        expected = math.exp(3.0)
        assert abs(compute_perplexity(3.0) - expected) < 0.01

    def test_known_value_loss_5(self):
        """Perplexity at loss=5.0 should be approximately exp(5.0)."""
        expected = math.exp(5.0)
        assert abs(compute_perplexity(5.0) - expected) < 0.01

    def test_small_loss(self):
        """Perplexity for a very small loss should be close to 1.0."""
        result = compute_perplexity(0.001)
        assert result > 1.0
        assert result < 1.01

    def test_returns_float(self):
        """compute_perplexity should return a float."""
        result = compute_perplexity(2.0)
        assert isinstance(result, float)


class TestComputeAccuracy:
    """Tests for the compute_accuracy function."""

    def test_returns_float(self):
        """compute_accuracy should return a float."""
        result = compute_accuracy([], [])
        assert isinstance(result, float)

    def test_empty_inputs(self):
        """compute_accuracy with empty lists should return 0.0."""
        result = compute_accuracy([], [])
        assert result == 0.0

    def test_stub_returns_zero(self):
        """The stub implementation always returns 0.0."""
        result = compute_accuracy([1, 2, 3], [1, 2, 4])
        assert result == 0.0
