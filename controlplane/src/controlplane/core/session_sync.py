"""Cross-surface session continuity (Unit 9).

A thin, dependency-free observation layer over :class:`SessionStore`. The store
is append-only; surfaces (terminal / ui / desktop) run as separate processes
sharing one SQLite file. To make the single conversation *observable* across
those processes we expose two helpers built on a read-only cursor:

- :func:`tail`  — turns appended since an ``id`` cursor (one ``SELECT``).
- :func:`watch` — block-poll until new turns appear or a timeout elapses.

Both open their own short-lived read connection to the same db file, so a
surface can follow turns written by any other surface without sharing objects.
The ``id`` cursor is the stable AUTOINCREMENT primary key of the ``turns`` table
(monotonic, never reused), which is why it is a reliable "have I seen this?"
marker even though :class:`ChatTurn` itself carries no id.
"""

from __future__ import annotations

import json
import sqlite3
import time

from .contract import ChatTurn
from .session import SessionStore

#: Polling cadence for :func:`watch`. Small enough to feel live in a chat REPL,
#: large enough to avoid busy-spinning the db file.
_POLL_INTERVAL = 0.05


def tail(store: SessionStore, after_id: int | None = None) -> list[tuple[int, ChatTurn]]:
    """Return ``(id, ChatTurn)`` for every turn newer than ``after_id``.

    Reads the same db file the ``store`` writes to via its own read-only
    connection, so a surface can observe turns appended by *other* surface
    processes. ``after_id`` is exclusive: pass the last id you have already seen
    and you get only what arrived since. ``None`` (the default) returns the full
    history, oldest-first.
    """
    cursor = -1 if after_id is None else after_id
    sql = (
        "SELECT id, role, text, surface, ts, data "
        "FROM turns WHERE id > ? ORDER BY id"
    )
    conn = sqlite3.connect(str(store.db_path), timeout=5.0)
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        rows = conn.execute(sql, (cursor,)).fetchall()
    finally:
        conn.close()
    return [
        (
            rid,
            ChatTurn(role=role, text=text, surface=surface, ts=ts, data=json.loads(data)),
        )
        for (rid, role, text, surface, ts, data) in rows
    ]


def watch(
    store: SessionStore, after_id: int, timeout: float
) -> list[tuple[int, ChatTurn]]:
    """Block until turns newer than ``after_id`` exist, or ``timeout`` elapses.

    Returns as soon as :func:`tail` yields anything — including immediately if
    data is already present — otherwise polls every ``_POLL_INTERVAL`` seconds
    and returns an empty list once ``timeout`` is exceeded. Dependency-free
    (plain sleep loop); intended for a surface following the shared conversation.
    """
    deadline = time.monotonic() + timeout
    while True:
        new = tail(store, after_id=after_id)
        if new:
            return new
        if time.monotonic() >= deadline:
            return []
        time.sleep(_POLL_INTERVAL)
