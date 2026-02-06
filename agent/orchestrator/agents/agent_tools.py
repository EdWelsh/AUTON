"""Tool executor factory - creates tool executors bound to a specific workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Coroutine

from orchestrator.comms.git_workspace import GitWorkspace


class ToolExecutor:
    """Binds tool execution to a specific workspace and config.

    Used by the orchestration engine to create per-agent tool executors
    that are sandboxed to the correct workspace and branch.
    """

    def __init__(self, workspace: GitWorkspace, kernel_spec_path: Path):
        self.workspace = workspace
        self.kernel_spec_path = kernel_spec_path
        self._file_writes: list[str] = []

    @property
    def files_written(self) -> list[str]:
        """Files written during this executor's lifetime."""
        return list(self._file_writes)

    def track_write(self, path: str) -> None:
        """Track a file write."""
        if path not in self._file_writes:
            self._file_writes.append(path)

    def reset_tracking(self) -> None:
        """Reset file write tracking."""
        self._file_writes.clear()
