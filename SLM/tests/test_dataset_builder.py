"""Unit tests for SLM.tools.dataset_builder module."""

import sys
from pathlib import Path

# Ensure the SLM package root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.dataset_builder import analyze_dataset, clean_dataset


class TestAnalyzeDataset:
    """Tests for the analyze_dataset function."""

    def test_returns_dict(self):
        """analyze_dataset should always return a dict."""
        result = analyze_dataset("/nonexistent/path")
        assert isinstance(result, dict)

    def test_has_files_key(self):
        """Result should contain a 'files' key."""
        result = analyze_dataset("/nonexistent/path")
        assert "files" in result

    def test_has_tokens_key(self):
        """Result should contain a 'tokens' key."""
        result = analyze_dataset("/nonexistent/path")
        assert "tokens" in result

    def test_has_vocab_size_key(self):
        """Result should contain a 'vocab_size' key."""
        result = analyze_dataset("/nonexistent/path")
        assert "vocab_size" in result

    def test_values_are_numeric(self):
        """All values in the result should be numeric (int or float)."""
        result = analyze_dataset("/nonexistent/path")
        for key in ("files", "tokens", "vocab_size"):
            assert isinstance(result[key], (int, float)), (
                f"Expected numeric value for '{key}', got {type(result[key])}"
            )

    def test_stub_returns_zeros(self):
        """The stub implementation should return zero counts."""
        result = analyze_dataset("/nonexistent/path")
        assert result["files"] == 0
        assert result["tokens"] == 0
        assert result["vocab_size"] == 0


class TestCleanDataset:
    """Tests for the clean_dataset function."""

    def test_does_not_raise(self):
        """clean_dataset should not raise when called with nonexistent paths."""
        clean_dataset("/nonexistent/input", "/nonexistent/output")

    def test_returns_none(self):
        """clean_dataset should return None (it operates via side effects)."""
        result = clean_dataset("/nonexistent/input", "/nonexistent/output")
        assert result is None
