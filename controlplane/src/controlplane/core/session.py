"""Persistent, cross-surface chat session.

One continuous conversation is shared by the terminal, UI, and desktop installs.
We back it with SQLite (WAL mode) at ``~/.auton/session.db`` so multiple surface
processes can append and read concurrently without clobbering a JSON file — the
key requirement for "maintain that chat from terminal / ui / desktop install".

The serialization shape mirrors ``agent/orchestrator/comms/message_bus.py``
(role/text/ts + a JSON ``data`` blob), persisted like
``agent/orchestrator/core/state.py``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .contract import ChatTurn

DEFAULT_DB_PATH = Path.home() / ".auton" / "session.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    role    TEXT NOT NULL,
    text    TEXT NOT NULL,
    surface TEXT NOT NULL,
    ts      REAL NOT NULL,
    data    TEXT NOT NULL DEFAULT '{}'
);
"""


class SessionStore:
    """Append-only store of :class:`ChatTurn` rows, safe for concurrent surfaces."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        # WAL lets readers and a writer coexist across surface processes.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def append(self, turn: ChatTurn) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO turns(role, text, surface, ts, data) VALUES (?, ?, ?, ?, ?)",
                (turn.role, turn.text, turn.surface, turn.ts, json.dumps(turn.data)),
            )

    def record(self, role: str, text: str, surface: str = "terminal", **data: object) -> ChatTurn:
        """Convenience: build a turn, persist it, return it."""
        turn = ChatTurn(role=role, text=text, surface=surface, data=dict(data))
        self.append(turn)
        return turn

    def history(self, limit: int | None = None) -> list[ChatTurn]:
        """Return turns oldest-first (optionally only the last ``limit``)."""
        sql = "SELECT role, text, surface, ts, data FROM turns ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        turns = [
            ChatTurn(role=r, text=t, surface=s, ts=ts, data=json.loads(d))
            for (r, t, s, ts, d) in rows
        ]
        if limit is not None:
            return turns[-limit:]
        return turns

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM turns")
