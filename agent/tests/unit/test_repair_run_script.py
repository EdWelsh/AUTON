"""scripts/repair_run.py builds a generation run on a failed attempt's tree, with the run's gates."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("repair_run", ROOT / "scripts" / "repair_run.py")
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)


def test_the_command_uses_the_failed_tree_the_runs_gates_and_the_gate_output(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "OUT", tmp_path / "repair")
    attempt = tmp_path / "r2-storage-attempt2"
    (attempt / "ws").mkdir(parents=True)
    (attempt / "RESULT.json").write_text(json.dumps({"gates": [
        {"cmd": "g.sh", "rc": 1, "tail": ['  "_fat32_list", referenced from:']},
        {"cmd": "ok.sh", "rc": 0, "tail": ["PASS"]}]}))
    cmd, out = rr.build("r2-storage", attempt, 1)
    assert cmd[cmd.index("--base-tree") + 1] == str(attempt / "ws")
    assert cmd.count("--gate") >= 1 and "--sessions" in cmd
    goal = (out / "goal-input.txt").read_text()
    assert "fat32_list" in goal and "ok.sh" not in goal
