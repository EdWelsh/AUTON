"""Tests for orchestrator state management."""

import json
import time

import pytest

from orchestrator.core.state import OrchestratorState


# ---------------------------------------------------------------------------
# Creation with defaults
# ---------------------------------------------------------------------------

class TestOrchestratorStateCreation:
    def test_required_fields(self):
        state = OrchestratorState(run_id="run-1", goal="Build a kernel")
        assert state.run_id == "run-1"
        assert state.goal == "Build a kernel"

    def test_default_phase(self):
        state = OrchestratorState(run_id="r", goal="g")
        assert state.phase == "init"

    def test_default_counters(self):
        state = OrchestratorState(run_id="r", goal="g")
        assert state.tasks_created == 0
        assert state.tasks_completed == 0
        assert state.tasks_failed == 0

    def test_default_cost(self):
        state = OrchestratorState(run_id="r", goal="g")
        assert state.total_cost_usd == 0.0

    def test_default_agent_states(self):
        state = OrchestratorState(run_id="r", goal="g")
        assert state.agent_states == {}

    def test_default_errors(self):
        state = OrchestratorState(run_id="r", goal="g")
        assert state.errors == []

    def test_default_iteration(self):
        state = OrchestratorState(run_id="r", goal="g")
        assert state.iteration == 0

    def test_timestamps_populated(self):
        before = time.time()
        state = OrchestratorState(run_id="r", goal="g")
        after = time.time()
        assert before <= state.started_at <= after
        assert before <= state.updated_at <= after


# ---------------------------------------------------------------------------
# save / load round-trip
# ---------------------------------------------------------------------------

class TestSaveLoad:
    def test_save_creates_file(self, tmp_path):
        state = OrchestratorState(run_id="run-1", goal="test goal")
        path = tmp_path / "state.json"
        state.save(path)
        assert path.exists()

    def test_save_creates_parent_dirs(self, tmp_path):
        state = OrchestratorState(run_id="run-1", goal="test goal")
        path = tmp_path / "sub" / "dir" / "state.json"
        state.save(path)
        assert path.exists()

    def test_saved_file_is_valid_json(self, tmp_path):
        state = OrchestratorState(run_id="run-1", goal="test goal")
        path = tmp_path / "state.json"
        state.save(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["run_id"] == "run-1"
        assert data["goal"] == "test goal"

    def test_round_trip_preserves_fields(self, tmp_path):
        original = OrchestratorState(
            run_id="run-42",
            goal="Write tests",
            phase="developing",
            tasks_created=10,
            tasks_completed=5,
            tasks_failed=1,
            total_cost_usd=1.23,
            iteration=3,
        )
        path = tmp_path / "state.json"
        original.save(path)

        loaded = OrchestratorState.load(path)
        assert loaded.run_id == "run-42"
        assert loaded.goal == "Write tests"
        assert loaded.phase == "developing"
        assert loaded.tasks_created == 10
        assert loaded.tasks_completed == 5
        assert loaded.tasks_failed == 1
        assert loaded.total_cost_usd == pytest.approx(1.23)
        assert loaded.iteration == 3

    def test_round_trip_preserves_errors(self, tmp_path):
        state = OrchestratorState(run_id="r", goal="g")
        state.record_error("agent-1", "something went wrong", task_id="t-1")
        path = tmp_path / "state.json"
        state.save(path)

        loaded = OrchestratorState.load(path)
        assert len(loaded.errors) == 1
        assert loaded.errors[0]["agent_id"] == "agent-1"
        assert loaded.errors[0]["error"] == "something went wrong"
        assert loaded.errors[0]["task_id"] == "t-1"

    def test_round_trip_preserves_agent_states(self, tmp_path):
        state = OrchestratorState(run_id="r", goal="g")
        state.agent_states = {"dev-1": "idle", "rev-1": "executing"}
        path = tmp_path / "state.json"
        state.save(path)

        loaded = OrchestratorState.load(path)
        assert loaded.agent_states == {"dev-1": "idle", "rev-1": "executing"}

    def test_save_updates_updated_at(self, tmp_path):
        state = OrchestratorState(run_id="r", goal="g")
        old_updated = state.updated_at
        # Small sleep to ensure time advances
        time.sleep(0.01)
        path = tmp_path / "state.json"
        state.save(path)
        assert state.updated_at >= old_updated


# ---------------------------------------------------------------------------
# load_or_create
# ---------------------------------------------------------------------------

class TestLoadOrCreate:
    def test_creates_new_when_path_does_not_exist(self, tmp_path):
        path = tmp_path / "nonexistent" / "state.json"
        state = OrchestratorState.load_or_create(path, run_id="new-run", goal="new goal")

        assert state.run_id == "new-run"
        assert state.goal == "new goal"
        assert state.phase == "init"
        # File should have been created
        assert path.exists()

    def test_loads_existing_when_path_exists(self, tmp_path):
        path = tmp_path / "state.json"
        # Create and save an existing state
        existing = OrchestratorState(
            run_id="existing-run",
            goal="existing goal",
            phase="testing",
            tasks_created=7,
        )
        existing.save(path)

        loaded = OrchestratorState.load_or_create(
            path, run_id="ignored-run", goal="ignored goal"
        )
        assert loaded.run_id == "existing-run"
        assert loaded.goal == "existing goal"
        assert loaded.phase == "testing"
        assert loaded.tasks_created == 7


# ---------------------------------------------------------------------------
# record_error
# ---------------------------------------------------------------------------

class TestRecordError:
    def test_appends_to_errors(self):
        state = OrchestratorState(run_id="r", goal="g")
        state.record_error("agent-x", "oops")
        assert len(state.errors) == 1

    def test_error_structure(self):
        state = OrchestratorState(run_id="r", goal="g")
        before = time.time()
        state.record_error("agent-x", "bad thing", task_id="task-5")
        after = time.time()

        err = state.errors[0]
        assert err["agent_id"] == "agent-x"
        assert err["error"] == "bad thing"
        assert err["task_id"] == "task-5"
        assert before <= err["timestamp"] <= after

    def test_error_without_task_id(self):
        state = OrchestratorState(run_id="r", goal="g")
        state.record_error("agent-x", "crash")
        assert state.errors[0]["task_id"] is None

    def test_multiple_errors(self):
        state = OrchestratorState(run_id="r", goal="g")
        state.record_error("a1", "err1")
        state.record_error("a2", "err2")
        state.record_error("a1", "err3", task_id="t-9")
        assert len(state.errors) == 3
        assert state.errors[0]["agent_id"] == "a1"
        assert state.errors[1]["agent_id"] == "a2"
        assert state.errors[2]["task_id"] == "t-9"
