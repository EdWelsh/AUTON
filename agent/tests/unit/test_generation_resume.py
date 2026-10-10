"""A run paused before planning finished starts again instead of being refused (w23)."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "generation_run", Path(__file__).resolve().parents[3] / "scripts" / "generation_run.py")
gr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gr)


def _state(ws, graph):
    (ws / ".auton").mkdir(parents=True)
    (ws / ".auton/state.json").write_text(json.dumps({"graph": graph}))


def test_no_state_means_a_fresh_run(tmp_path):
    assert gr.can_resume(tmp_path) is False


def test_state_without_a_graph_is_not_resumable(tmp_path):
    _state(tmp_path, {})
    assert gr.can_resume(tmp_path) is False


def test_a_saved_graph_is_resumable(tmp_path):
    _state(tmp_path, {"t1": {"id": "t1"}})
    assert gr.can_resume(tmp_path) is True


def test_a_corrupt_state_file_is_not_resumable(tmp_path):
    (tmp_path / ".auton").mkdir()
    (tmp_path / ".auton/state.json").write_text("{")
    assert gr.can_resume(tmp_path) is False
