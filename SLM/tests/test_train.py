"""Unit tests for SLM training script (scripts/train.py)."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "train.py"


class TestTrainScript:
    """Tests for the train.py CLI script."""

    def test_script_exists(self):
        """The train.py script should exist on disk."""
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"

    def test_help_flag(self):
        """train.py --help should exit cleanly and show usage info."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        stdout_lower = result.stdout.lower()
        assert "config" in stdout_lower or "usage" in stdout_lower

    def test_help_mentions_dataset(self):
        """train.py --help should mention the --dataset argument."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert "dataset" in result.stdout.lower()

    def test_help_mentions_output(self):
        """train.py --help should mention the --output option."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert "output" in result.stdout.lower()

    def test_missing_required_args(self):
        """train.py without required args should fail with non-zero exit code."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
