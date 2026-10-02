"""Persistent orchestration state for crash recovery."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

STATE_FORMAT = 2


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
    # Format 2 (w17) persists what a resume needs. Format 1 saved counters only,
    # so despite this module's docstring nothing could be recovered from it.
    format: int = STATE_FORMAT
    graph: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    head_at_save: str = ""      # main's commit when paused; a resume refuses if it moved
    resume_count: int = 0
    design_adopted: bool = False   # phase 2 finished; a resume skips it
    designed: list[str] = field(default_factory=list)  # subsystems already designed
    subject_hash: str = ""   # tree hash of a staged application (A2), if any

    def save(self, path: Path) -> None:
        """Save state to a JSON file, atomically: a kill mid-write must not
        leave a truncated file where the only copy of the graph was."""
        self.updated_at = time.time()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> OrchestratorState:
        """Load state from disk. A file with no `format` predates format 2."""
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("format", 1)
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
