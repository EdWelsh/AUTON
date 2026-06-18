"""Cross-surface session continuity (Unit 9).

These tests prove the one-continuous-conversation requirement: turns appended by
one surface process are observable from another surface reading the SAME SQLite
db file. No mocks — two real :class:`SessionStore` instances over one real file.
"""

from __future__ import annotations

import time

import pytest

from controlplane.core import ChatTurn, SessionStore
from controlplane.core.session_sync import tail, watch


@pytest.mark.integration
def test_tail_sees_other_surfaces_turn(tmp_path):
    db = tmp_path / "session.db"

    # "terminal" surface appends a turn.
    terminal = SessionStore(db)
    terminal.record("user", "hello from terminal", surface="terminal")

    # A SECOND store on the SAME db file, as the "ui" surface, sees it.
    ui = SessionStore(db)
    seen = tail(ui)
    assert [t.text for _, t in seen] == ["hello from terminal"]
    assert seen[0][1].surface == "terminal"
    assert all(isinstance(rid, int) for rid, _ in seen)

    # ui appends; terminal, tailing after its last cursor, sees ONLY the new one.
    last_id = seen[-1][0]
    ui.record("auton", "reply from ui", surface="ui")
    fresh = tail(terminal, after_id=last_id)
    assert [t.text for _, t in fresh] == ["reply from ui"]
    assert fresh[0][1].surface == "ui"


@pytest.mark.unit
def test_cursor_excludes_seen_turns(tmp_path):
    db = tmp_path / "session.db"
    store = SessionStore(db)
    store.record("user", "one")
    store.record("user", "two")
    store.record("user", "three")

    all_turns = tail(store)
    assert [t.text for _, t in all_turns] == ["one", "two", "three"]
    assert [rid for rid, _ in all_turns] == sorted(rid for rid, _ in all_turns)

    # after_id of the first row excludes it; only later rows return.
    first_id = all_turns[0][0]
    rest = tail(store, after_id=first_id)
    assert [t.text for _, t in rest] == ["two", "three"]

    # after_id of the last row -> nothing new.
    last_id = all_turns[-1][0]
    assert tail(store, after_id=last_id) == []


@pytest.mark.unit
def test_tail_returns_chatturns(tmp_path):
    db = tmp_path / "session.db"
    store = SessionStore(db)
    store.record("user", "hi", surface="desktop", foo="bar")

    [(rid, turn)] = tail(store)
    assert isinstance(turn, ChatTurn)
    assert turn.role == "user"
    assert turn.surface == "desktop"
    assert turn.data == {"foo": "bar"}
    assert rid > 0


@pytest.mark.unit
def test_watch_returns_promptly_when_data_exists(tmp_path):
    db = tmp_path / "session.db"
    store = SessionStore(db)
    store.record("user", "already here")

    start = time.monotonic()
    got = watch(store, after_id=0, timeout=5.0)
    elapsed = time.monotonic() - start

    assert [t.text for _, t in got] == ["already here"]
    assert elapsed < 1.0  # did not burn the whole timeout


@pytest.mark.unit
def test_watch_times_out_to_empty_when_no_new_turns(tmp_path):
    db = tmp_path / "session.db"
    store = SessionStore(db)
    store.record("user", "seen")
    [(last_id, _)] = tail(store)

    start = time.monotonic()
    got = watch(store, after_id=last_id, timeout=0.3)
    elapsed = time.monotonic() - start

    assert got == []
    assert elapsed >= 0.3
