"""Unit tests for SLM.tools.gguf_validator module."""

import sys
from pathlib import Path

# Ensure the SLM package root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.gguf_validator import validate_gguf


class TestValidateGgufNonexistent:
    """Tests for validate_gguf with a file that does not exist."""

    def test_nonexistent_file_invalid(self):
        """A nonexistent file should be marked as invalid."""
        result = validate_gguf("/nonexistent/model.gguf")
        assert result["valid"] is False

    def test_nonexistent_file_has_error(self):
        """A nonexistent file result should contain an 'error' key."""
        result = validate_gguf("/nonexistent/model.gguf")
        assert "error" in result

    def test_nonexistent_file_error_message(self):
        """The error message should indicate the file was not found."""
        result = validate_gguf("/nonexistent/model.gguf")
        assert "not found" in result["error"].lower()


class TestValidateGgufExisting:
    """Tests for validate_gguf with a file that exists."""

    def test_existing_file_valid(self, tmp_path):
        """An existing file should be marked as valid."""
        fake_gguf = tmp_path / "model.gguf"
        fake_gguf.write_bytes(b"\x00" * 1024)
        result = validate_gguf(str(fake_gguf))
        assert result["valid"] is True

    def test_existing_file_has_size(self, tmp_path):
        """An existing file result should contain a 'size_mb' key."""
        fake_gguf = tmp_path / "model.gguf"
        fake_gguf.write_bytes(b"\x00" * 1024)
        result = validate_gguf(str(fake_gguf))
        assert "size_mb" in result

    def test_existing_file_size_positive(self, tmp_path):
        """The size_mb value should be positive for a non-empty file."""
        fake_gguf = tmp_path / "model.gguf"
        fake_gguf.write_bytes(b"\x00" * 1024)
        result = validate_gguf(str(fake_gguf))
        assert result["size_mb"] > 0

    def test_existing_file_size_correct(self, tmp_path):
        """The size_mb value should match the actual file size."""
        data = b"\x00" * (1024 * 1024)  # 1 MiB
        fake_gguf = tmp_path / "model_1mb.gguf"
        fake_gguf.write_bytes(data)
        result = validate_gguf(str(fake_gguf))
        assert abs(result["size_mb"] - 1.0) < 0.01

    def test_no_error_key_for_valid_file(self, tmp_path):
        """A valid file result should not contain an 'error' key."""
        fake_gguf = tmp_path / "model.gguf"
        fake_gguf.write_bytes(b"\x00" * 512)
        result = validate_gguf(str(fake_gguf))
        assert "error" not in result
