"""Persistent orchestration state for crash recovery."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class OrchestratorState:
    """Global state of the orchestration run.

    Persisted to disk so the system can recover from crashes.
    """

    run_id: str
    goal: str
    phase: str = "init"  # init, planning, designing, developing, testing, integrating, done
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    tasks_created: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_cost_usd: float = 0.0
    agent_states: dict[str, str] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    iteration: int = 0

    def save(self, path: Path) -> None:
        """Save state to a JSON file."""
        self.updated_at = time.time()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> OrchestratorState:
        """Load state from disk."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)

    @classmethod
    def load_or_create(cls, path: Path, run_id: str, goal: str) -> OrchestratorState:
        """Load existing state or create new."""
        if path.exists():
            return cls.load(path)
        state = cls(run_id=run_id, goal=goal)
        state.save(path)
        return state

    def record_error(self, agent_id: str, error: str, task_id: str | None = None) -> None:
        self.errors.append({
            "agent_id": agent_id,
            "error": error,
            "task_id": task_id,
            "timestamp": time.time(),
        })
