"""Unit tests for SLM.tools.tokenizer module."""

import sys
from pathlib import Path

# Ensure the SLM package root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.tokenizer import train_tokenizer, tokenize_dataset


class TestTrainTokenizer:
    """Tests for the train_tokenizer function."""

    def test_returns_dict(self):
        """train_tokenizer should return a dict."""
        result = train_tokenizer("/fake/path")
        assert isinstance(result, dict)

    def test_default_vocab_size(self):
        """Default vocab_size should be 32000."""
        result = train_tokenizer("/fake/path")
        assert result["vocab_size"] == 32000

    def test_custom_vocab_size(self):
        """Custom vocab_size should be reflected in the result."""
        result = train_tokenizer("/fake/path", vocab_size=16000)
        assert result["vocab_size"] == 16000

    def test_small_vocab_size(self):
        """A small vocab_size should be accepted."""
        result = train_tokenizer("/fake/path", vocab_size=256)
        assert result["vocab_size"] == 256

    def test_large_vocab_size(self):
        """A large vocab_size should be accepted."""
        result = train_tokenizer("/fake/path", vocab_size=100000)
        assert result["vocab_size"] == 100000

    def test_result_has_vocab_size_key(self):
        """The result dict must contain the 'vocab_size' key."""
        result = train_tokenizer("/fake/path")
        assert "vocab_size" in result


class TestTokenizeDataset:
    """Tests for the tokenize_dataset function."""

    def test_does_not_raise(self):
        """tokenize_dataset should not raise when called with fake paths."""
        tokenize_dataset("/fake/input", "/fake/output", "/fake/vocab")

    def test_returns_none(self):
        """tokenize_dataset should return None."""
        result = tokenize_dataset("/fake/input", "/fake/output", "/fake/vocab")
        assert result is None
