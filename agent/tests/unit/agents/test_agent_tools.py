"""Tests for ToolExecutor from agent_tools."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.agents.agent_tools import ToolExecutor


@pytest.fixture
def mock_workspace():
    return MagicMock()


@pytest.fixture
def executor(mock_workspace):
    return ToolExecutor(
        workspace=mock_workspace,
        kernel_spec_path=Path("/tmp/specs"),
    )


class TestToolExecutorCreation:
    def test_creation(self, executor, mock_workspace):
        assert executor.workspace is mock_workspace
        assert executor.kernel_spec_path == Path("/tmp/specs")

    def test_initial_files_written_empty(self, executor):
        assert executor.files_written == []

    def test_internal_list_empty(self, executor):
        assert executor._file_writes == []


class TestTrackWrite:
    def test_track_single(self, executor):
        executor.track_write("kernel/boot.c")
        assert "kernel/boot.c" in executor.files_written

    def test_track_multiple(self, executor):
        executor.track_write("a.c")
        executor.track_write("b.c")
        executor.track_write("c.h")
        assert executor.files_written == ["a.c", "b.c", "c.h"]

    def test_deduplication(self, executor):
        executor.track_write("kernel/mm.c")
        executor.track_write("kernel/mm.c")
        executor.track_write("kernel/mm.c")
        assert executor.files_written == ["kernel/mm.c"]

    def test_dedup_preserves_order(self, executor):
        executor.track_write("first.c")
        executor.track_write("second.c")
        executor.track_write("first.c")
        assert executor.files_written == ["first.c", "second.c"]


class TestFilesWrittenProperty:
    def test_returns_copy(self, executor):
        executor.track_write("x.c")
        result = executor.files_written
        result.append("should_not_appear.c")
        assert "should_not_appear.c" not in executor.files_written

    def test_returns_list(self, executor):
        assert isinstance(executor.files_written, list)

    def test_reflects_tracked_writes(self, executor):
        executor.track_write("a.c")
        executor.track_write("b.c")
        fw = executor.files_written
        assert len(fw) == 2
        assert fw[0] == "a.c"
        assert fw[1] == "b.c"


class TestResetTracking:
    def test_clears_tracked_writes(self, executor):
        executor.track_write("a.c")
        executor.track_write("b.c")
        executor.reset_tracking()
        assert executor.files_written == []

    def test_reset_then_track(self, executor):
        executor.track_write("old.c")
        executor.reset_tracking()
        executor.track_write("new.c")
        assert executor.files_written == ["new.c"]

    def test_double_reset(self, executor):
        executor.track_write("a.c")
        executor.reset_tracking()
        executor.reset_tracking()
        assert executor.files_written == []
