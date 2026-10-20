"""scripts/run-status.py reads a run's events and says what is in flight and what each task did."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2].parent
spec = importlib.util.spec_from_file_location("run_status", ROOT / "scripts" / "run-status.py")
run_status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_status)

T = "2026-10-20T12:00:%02d.000000Z"


def _write(tmp_path, rows):
    (tmp_path / "events.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n{cut")


def test_a_run_with_no_events_says_so(tmp_path):
    assert "no events yet" in run_status.render(run_status.summarise(run_status.load(tmp_path)))


def test_summary_counts_calls_tasks_reviews_and_the_stall_clock(tmp_path):
    _write(tmp_path, [
        {"t": T % 1, "kind": "task_start", "task": "mm-001", "title": "headers", "agent": "dev-01"},
        {"t": T % 2, "kind": "llm_call", "agent": "dev-01", "prompt_tokens": 1000,
         "completion_tokens": 100, "seconds": 10.0},
        {"t": T % 3, "kind": "tool_call", "agent": "dev-01", "name": "build_kernel", "seconds": 90},
        {"t": T % 4, "kind": "task_result", "task": "mm-001", "success": True},
        {"t": T % 5, "kind": "review", "task": "mm-001", "by": "syntax_gate",
         "verdict": "request_changes"},
        {"t": T % 6, "kind": "task_start", "task": "mm-001", "agent": "dev-01"},
        {"t": T % 7, "kind": "review", "task": "mm-001", "by": "reviewer-01", "verdict": "approve"},
        {"t": T % 8, "kind": "merge", "task": "mm-001", "ok": True},
        {"t": T % 9, "kind": "task_start", "task": "mm-002", "title": "pmm", "agent": "dev-01"},
    ])
    now = datetime(2026, 10, 20, 12, 5, 9, tzinfo=timezone.utc)
    s = run_status.summarise(run_status.load(tmp_path), now=now)
    assert s["events"] == 9 and s["seconds_since_last_event"] == 300      # the cut line is skipped
    assert s["current"]["task"] == "mm-002"
    a = s["agents"]["dev-01"]
    assert a["calls"] == 1 and a["completion_tokens_per_second"] == 10.0 and a["tool_calls"] == 1
    t = s["tasks"]["mm-001"]
    assert t["state"] == "merged" and t["starts"] == 2
    assert [r["verdict"] for r in t["reviews"]] == ["request_changes", "approve"]
    assert s["slow_tools"][0]["name"] == "build_kernel"
    assert "mm-002" in run_status.render(s)
