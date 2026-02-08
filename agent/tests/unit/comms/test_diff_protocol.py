"""Tests for the structured diff protocol (TaskMetadata and TaskStatus)."""

import json
import time

import pytest

from orchestrator.comms.diff_protocol import TaskMetadata, TaskStatus


# ---------------------------------------------------------------------------
# TaskStatus enum
# ---------------------------------------------------------------------------

class TestTaskStatus:
    def test_pending(self):
        assert TaskStatus.PENDING.value == "pending"

    def test_in_progress(self):
        assert TaskStatus.IN_PROGRESS.value == "in_progress"

    def test_review(self):
        assert TaskStatus.REVIEW.value == "review"

    def test_approved(self):
        assert TaskStatus.APPROVED.value == "approved"

    def test_rejected(self):
        assert TaskStatus.REJECTED.value == "rejected"

    def test_merged(self):
        assert TaskStatus.MERGED.value == "merged"

    def test_blocked(self):
        assert TaskStatus.BLOCKED.value == "blocked"

    def test_is_str_subclass(self):
        assert isinstance(TaskStatus.PENDING, str)

    def test_all_values_unique(self):
        values = [s.value for s in TaskStatus]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# TaskMetadata creation
# ---------------------------------------------------------------------------

class TestTaskMetadataCreation:
    def test_required_fields(self):
        tm = TaskMetadata(
            task_id="task-1",
            title="Implement boot",
            subsystem="boot",
            agent_id="dev-1",
            branch="agent/dev-1/boot-init",
        )
        assert tm.task_id == "task-1"
        assert tm.title == "Implement boot"
        assert tm.subsystem == "boot"
        assert tm.agent_id == "dev-1"
        assert tm.branch == "agent/dev-1/boot-init"

    def test_default_status(self):
        tm = TaskMetadata(
            task_id="t", title="t", subsystem="s", agent_id="a", branch="b"
        )
        assert tm.status == TaskStatus.IN_PROGRESS

    def test_default_description(self):
        tm = TaskMetadata(
            task_id="t", title="t", subsystem="s", agent_id="a", branch="b"
        )
        assert tm.description == ""

    def test_default_spec_reference(self):
        tm = TaskMetadata(
            task_id="t", title="t", subsystem="s", agent_id="a", branch="b"
        )
        assert tm.spec_reference == ""

    def test_default_lists(self):
        tm = TaskMetadata(
            task_id="t", title="t", subsystem="s", agent_id="a", branch="b"
        )
        assert tm.dependencies == []
        assert tm.acceptance_criteria == []
        assert tm.review_comments == []

    def test_default_build_and_test_status(self):
        tm = TaskMetadata(
            task_id="t", title="t", subsystem="s", agent_id="a", branch="b"
        )
        assert tm.build_status == "unknown"
        assert tm.test_status == "unknown"

    def test_timestamps_populated(self):
        before = time.time()
        tm = TaskMetadata(
            task_id="t", title="t", subsystem="s", agent_id="a", branch="b"
        )
        after = time.time()
        assert before <= tm.created_at <= after
        assert before <= tm.updated_at <= after

    def test_custom_status(self):
        tm = TaskMetadata(
            task_id="t", title="t", subsystem="s", agent_id="a", branch="b",
            status=TaskStatus.APPROVED,
        )
        assert tm.status == TaskStatus.APPROVED


# ---------------------------------------------------------------------------
# to_json / from_json round-trip
# ---------------------------------------------------------------------------

class TestTaskMetadataJson:
    def _make_sample(self) -> TaskMetadata:
        return TaskMetadata(
            task_id="task-42",
            title="Implement memory allocator",
            subsystem="mm",
            agent_id="dev-3",
            branch="agent/dev-3/mm-alloc",
            status=TaskStatus.REVIEW,
            description="Page-frame allocator using buddy system",
            spec_reference="mm.md#allocator",
            dependencies=["task-10", "task-11"],
            acceptance_criteria=["boots", "passes tests"],
            build_status="pass",
            test_status="pass",
            review_comments=[{"reviewer": "rev-1", "comment": "LGTM"}],
        )

    def test_to_json_is_valid_json(self):
        tm = self._make_sample()
        raw = tm.to_json()
        data = json.loads(raw)
        assert data["task_id"] == "task-42"
        assert data["status"] == "review"  # serialized as string value

    def test_from_json_restores_fields(self):
        tm = self._make_sample()
        restored = TaskMetadata.from_json(tm.to_json())
        assert restored.task_id == "task-42"
        assert restored.title == "Implement memory allocator"
        assert restored.subsystem == "mm"
        assert restored.agent_id == "dev-3"
        assert restored.branch == "agent/dev-3/mm-alloc"
        assert restored.status == TaskStatus.REVIEW
        assert restored.description == "Page-frame allocator using buddy system"
        assert restored.spec_reference == "mm.md#allocator"
        assert restored.dependencies == ["task-10", "task-11"]
        assert restored.acceptance_criteria == ["boots", "passes tests"]
        assert restored.build_status == "pass"
        assert restored.test_status == "pass"
        assert restored.review_comments == [{"reviewer": "rev-1", "comment": "LGTM"}]

    def test_round_trip_preserves_timestamps(self):
        tm = self._make_sample()
        restored = TaskMetadata.from_json(tm.to_json())
        assert restored.created_at == pytest.approx(tm.created_at)
        assert restored.updated_at == pytest.approx(tm.updated_at)

    def test_round_trip_all_statuses(self):
        for status in TaskStatus:
            tm = TaskMetadata(
                task_id="t", title="t", subsystem="s", agent_id="a", branch="b",
                status=status,
            )
            restored = TaskMetadata.from_json(tm.to_json())
            assert restored.status == status


# ---------------------------------------------------------------------------
# save / load from disk
# ---------------------------------------------------------------------------

class TestTaskMetadataDisk:
    def test_save_creates_file(self, tmp_path):
        tm = TaskMetadata(
            task_id="task-disk-1",
            title="Boot",
            subsystem="boot",
            agent_id="dev-1",
            branch="b",
        )
        tm.save(tmp_path)
        expected = tmp_path / ".auton" / "tasks" / "task-disk-1.json"
        assert expected.exists()

    def test_save_creates_directories(self, tmp_path):
        workspace = tmp_path / "deep" / "workspace"
        tm = TaskMetadata(
            task_id="task-dirs",
            title="t",
            subsystem="s",
            agent_id="a",
            branch="b",
        )
        tm.save(workspace)
        assert (workspace / ".auton" / "tasks" / "task-dirs.json").exists()

    def test_save_updates_updated_at(self, tmp_path):
        tm = TaskMetadata(
            task_id="task-ts",
            title="t",
            subsystem="s",
            agent_id="a",
            branch="b",
        )
        old_updated = tm.updated_at
        time.sleep(0.01)
        tm.save(tmp_path)
        assert tm.updated_at >= old_updated

    def test_load_round_trip(self, tmp_path):
        original = TaskMetadata(
            task_id="task-rt",
            title="Round trip test",
            subsystem="sched",
            agent_id="dev-2",
            branch="agent/dev-2/sched-rr",
            status=TaskStatus.APPROVED,
            description="Round-robin scheduler",
            dependencies=["task-0"],
        )
        original.save(tmp_path)

        loaded = TaskMetadata.load(tmp_path, "task-rt")
        assert loaded.task_id == "task-rt"
        assert loaded.title == "Round trip test"
        assert loaded.subsystem == "sched"
        assert loaded.agent_id == "dev-2"
        assert loaded.branch == "agent/dev-2/sched-rr"
        assert loaded.status == TaskStatus.APPROVED
        assert loaded.description == "Round-robin scheduler"
        assert loaded.dependencies == ["task-0"]

    def test_load_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            TaskMetadata.load(tmp_path, "does-not-exist")


# ---------------------------------------------------------------------------
# load_all
# ---------------------------------------------------------------------------

class TestTaskMetadataLoadAll:
    def test_load_all_returns_sorted_list(self, tmp_path):
        t_base = time.time()

        # Create tasks with different created_at timestamps
        t1 = TaskMetadata(
            task_id="task-c",
            title="Third",
            subsystem="s",
            agent_id="a",
            branch="b",
            created_at=t_base + 2,
        )
        t2 = TaskMetadata(
            task_id="task-a",
            title="First",
            subsystem="s",
            agent_id="a",
            branch="b",
            created_at=t_base,
        )
        t3 = TaskMetadata(
            task_id="task-b",
            title="Second",
            subsystem="s",
            agent_id="a",
            branch="b",
            created_at=t_base + 1,
        )

        t1.save(tmp_path)
        t2.save(tmp_path)
        t3.save(tmp_path)

        all_tasks = TaskMetadata.load_all(tmp_path)
        assert len(all_tasks) == 3
        # Should be sorted by created_at ascending
        assert all_tasks[0].task_id == "task-a"
        assert all_tasks[1].task_id == "task-b"
        assert all_tasks[2].task_id == "task-c"

    def test_load_all_empty_directory(self, tmp_path):
        result = TaskMetadata.load_all(tmp_path)
        assert result == []

    def test_load_all_with_tasks_dir_but_no_files(self, tmp_path):
        (tmp_path / ".auton" / "tasks").mkdir(parents=True)
        result = TaskMetadata.load_all(tmp_path)
        assert result == []

    def test_load_all_single_task(self, tmp_path):
        tm = TaskMetadata(
            task_id="only-one",
            title="Solo task",
            subsystem="s",
            agent_id="a",
            branch="b",
        )
        tm.save(tmp_path)
        all_tasks = TaskMetadata.load_all(tmp_path)
        assert len(all_tasks) == 1
        assert all_tasks[0].task_id == "only-one"
