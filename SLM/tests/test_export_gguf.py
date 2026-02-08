"""Unit tests for SLM GGUF export script (scripts/export_gguf.py)."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "export_gguf.py"


class TestExportGgufScript:
    """Tests for the export_gguf.py CLI script."""

    def test_script_exists(self):
        """The export_gguf.py script should exist on disk."""
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"

    def test_help_flag(self):
        """export_gguf.py --help should exit cleanly and show usage info."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        stdout_lower = result.stdout.lower()
        assert "model" in stdout_lower or "usage" in stdout_lower

    def test_help_mentions_output(self):
        """export_gguf.py --help should mention the --output option."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert "output" in result.stdout.lower()

    def test_help_mentions_model(self):
        """export_gguf.py --help should mention the --model option."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert "model" in result.stdout.lower()

    def test_missing_required_args(self):
        """export_gguf.py without required args should fail with non-zero exit code."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
