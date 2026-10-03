"""The run's budget is work, not time spent waiting on the provider's usage limits (2026-10-03)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "generation_run.py"
spec = importlib.util.spec_from_file_location("generation_run", SCRIPT)
gr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gr)


def test_waits_are_read_from_the_transcript(tmp_path):
    (tmp_path / "transcript-1.log").write_text(
        "WARNING [dev-01] subscription usage limit; waiting 15 min (monthly spend)\n"
        "INFO something\nWARNING [arch-01] subscription usage limit; waiting 15 min\n")
    assert gr.limit_wait_seconds(tmp_path, 1, 18000) == 1800


def test_a_wait_never_exceeds_the_session(tmp_path):
    (tmp_path / "transcript-2.log").write_text("waiting 15 min\n" * 30)
    assert gr.limit_wait_seconds(tmp_path, 2, 18000) == 18000


def test_no_transcript_no_wait(tmp_path):
    assert gr.limit_wait_seconds(tmp_path, 3, 100) == 0


def test_work_is_wall_clock_less_waits_and_a_memory_pause_is_none():
    assert gr.work_seconds({"seconds": 18000, "limit_wait_seconds": 17100}) == 900
    assert gr.work_seconds({"seconds": 500, "memory_paused": True}) == 0
    assert gr.work_seconds({"seconds": 600}) == 600
