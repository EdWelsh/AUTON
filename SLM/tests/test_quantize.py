"""Unit tests for SLM quantization script (scripts/quantize.py)."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "quantize.py"


class TestQuantizeScript:
    """Tests for the quantize.py CLI script."""

    def test_script_exists(self):
        """The quantize.py script should exist on disk."""
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"

    def test_help_flag(self):
        """quantize.py --help should exit cleanly and show usage info."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        stdout_lower = result.stdout.lower()
        assert "checkpoint" in stdout_lower or "usage" in stdout_lower

    def test_help_mentions_bits(self):
        """quantize.py --help should mention the --bits option."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert "bits" in result.stdout.lower()

    def test_help_mentions_output(self):
        """quantize.py --help should mention the --output option."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert "output" in result.stdout.lower()

    def test_missing_required_args(self):
        """quantize.py without required args should fail with non-zero exit code."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
