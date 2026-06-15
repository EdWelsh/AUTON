"""Unit tests for SLM.tools.gguf_validator module."""

import sys
from pathlib import Path

# Ensure the SLM package root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.gguf_validator import GGUF_MAGIC, make_minimal_header, validate_gguf


def _write_gguf(path: Path, tensor_count: int = 0, kv_count: int = 0, pad: int = 1024) -> Path:
    """Write a minimal valid GGUF file padded to a realistic size."""
    path.write_bytes(make_minimal_header(3, tensor_count, kv_count) + b"\x00" * pad)
    return path


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


class TestValidateGgufMalformed:
    """Tests for validate_gguf with files that are not valid GGUF."""

    def test_bad_magic_invalid(self, tmp_path):
        """A file without the GGUF magic should be invalid."""
        bad = tmp_path / "bad.gguf"
        bad.write_bytes(b"\x00" * 1024)
        result = validate_gguf(str(bad))
        assert result["valid"] is False
        assert "magic" in result["error"].lower()

    def test_too_small_invalid(self, tmp_path):
        """A file too small to hold a header should be invalid."""
        tiny = tmp_path / "tiny.gguf"
        tiny.write_bytes(GGUF_MAGIC)  # 4 bytes, shorter than full header
        result = validate_gguf(str(tiny))
        assert result["valid"] is False


class TestValidateGgufValid:
    """Tests for validate_gguf with a well-formed GGUF file."""

    def test_valid_file(self, tmp_path):
        """A file with a correct GGUF header should be valid."""
        result = validate_gguf(str(_write_gguf(tmp_path / "model.gguf")))
        assert result["valid"] is True

    def test_valid_file_has_size(self, tmp_path):
        """A valid file result should contain a 'size_mb' key."""
        result = validate_gguf(str(_write_gguf(tmp_path / "model.gguf")))
        assert "size_mb" in result

    def test_valid_file_size_positive(self, tmp_path):
        """The size_mb value should be positive for a non-empty file."""
        result = validate_gguf(str(_write_gguf(tmp_path / "model.gguf")))
        assert result["size_mb"] > 0

    def test_valid_file_reports_header_fields(self, tmp_path):
        """A valid file should report parsed version and tensor_count."""
        result = validate_gguf(str(_write_gguf(tmp_path / "m.gguf", tensor_count=5, kv_count=7)))
        assert result["version"] == 3
        assert result["tensor_count"] == 5
        assert result["kv_count"] == 7

    def test_no_error_key_for_valid_file(self, tmp_path):
        """A valid file result should not contain an 'error' key."""
        result = validate_gguf(str(_write_gguf(tmp_path / "model.gguf", pad=512)))
        assert "error" not in result
