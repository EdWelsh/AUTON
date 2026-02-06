"""Structured diff protocol for agent-proposed changes."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    MERGED = "merged"
    BLOCKED = "blocked"


@dataclass
class TaskMetadata:
    """Metadata for an agent-proposed change, stored alongside the git branch."""

    task_id: str
    title: str
    subsystem: str
    agent_id: str
    branch: str
    status: TaskStatus = TaskStatus.IN_PROGRESS
    description: str = ""
    spec_reference: str = ""
    dependencies: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    build_status: str = "unknown"
    test_status: str = "unknown"
    review_comments: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_json(self) -> str:
        data = asdict(self)
        data["status"] = self.status.value
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> TaskMetadata:
        data = json.loads(raw)
        data["status"] = TaskStatus(data["status"])
        return cls(**data)

    def save(self, workspace_path: Path) -> None:
        """Save task metadata to the .auton/tasks/ directory."""
        tasks_dir = workspace_path / ".auton" / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        path = tasks_dir / f"{self.task_id}.json"
        self.updated_at = time.time()
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, workspace_path: Path, task_id: str) -> TaskMetadata:
        """Load task metadata from disk."""
        path = workspace_path / ".auton" / "tasks" / f"{task_id}.json"
        return cls.from_json(path.read_text(encoding="utf-8"))

    @classmethod
    def load_all(cls, workspace_path: Path) -> list[TaskMetadata]:
        """Load all task metadata files."""
        tasks_dir = workspace_path / ".auton" / "tasks"
        if not tasks_dir.exists():
            return []
        tasks = []
        for path in tasks_dir.glob("*.json"):
            tasks.append(cls.from_json(path.read_text(encoding="utf-8")))
        return sorted(tasks, key=lambda t: t.created_at)
