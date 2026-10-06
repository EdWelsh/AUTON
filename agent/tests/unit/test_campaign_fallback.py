"""A failed phase's end-to-end-passing attempt is its dependants' base (amended 2026-10-06)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "campaign.py"
spec = importlib.util.spec_from_file_location("campaign_fb", SCRIPT)
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


def _finished(d: Path, rcs):
    (d / "ws").mkdir(parents=True)
    (d / "RESULT.json").write_text(json.dumps(
        {"finished": "x", "sessions": [], "gates": [{"rc": rc} for rc in rcs]}))


def test_a_failed_phase_with_a_tree_fallback_is_the_base(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, "OUT", tmp_path)
    _finished(tmp_path / "r2-attempt1", [1, 2])
    _finished(tmp_path / "r2-attempt2", [1, 0])
    runs = {"r2": {"name": "r2", "base": "kernel-base-v5", "fallback": "tree:r2-attempt2"},
            "r3": {"name": "r3", "base": "run:r2"}}
    args, note = campaign.base_for(runs["r3"], runs)
    assert args == ["--base-tree", str(tmp_path / "r2-attempt2" / "ws")] and "fallback" in note


def test_without_a_fallback_the_dependant_takes_the_failed_phases_own_base(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, "OUT", tmp_path)
    _finished(tmp_path / "r2-attempt1", [1])
    _finished(tmp_path / "r2-attempt2", [1])
    runs = {"r2": {"name": "r2", "base": "kernel-base-v5", "fallback": "none"},
            "r3": {"name": "r3", "base": "run:r2"}}
    assert campaign.base_for(runs["r3"], runs)[0] == ["--base-rev", "kernel-base-v5"]
