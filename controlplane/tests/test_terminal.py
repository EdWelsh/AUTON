"""Unit tests for the terminal chat REPL (Unit 5).

Drives the injectable ``run()`` with a fake input stream and a captured output
stream, against a *real* ChatEngine (no engine mocks) wired to a one-capability
in-memory Registry and a throwaway SQLite SessionStore.
"""

from __future__ import annotations

import io

from controlplane.core import (
    Capability,
    CapabilityResult,
    CapabilityStatus,
    ChatEngine,
    Registry,
    SessionStore,
)
from controlplane.surfaces.terminal.repl import run


def _fake_capability() -> Capability:
    return Capability(
        name="echo",
        keywords=("echo",),
        status=CapabilityStatus.WORKING,
        note="repeats your text back",
        handler=lambda text: CapabilityResult.ok(f"echo: {text}"),
    )


def _engine(tmp_path) -> ChatEngine:
    registry = Registry([_fake_capability()])
    session = SessionStore(tmp_path / "session.db")
    return ChatEngine(registry=registry, session=session, surface="terminal")


def test_run_prints_banner_and_capabilities_then_records_turns(tmp_path):
    # Arrange
    engine = _engine(tmp_path)
    in_stream = io.StringIO("what can you do\nquit\n")
    out_stream = io.StringIO()

    # Act
    run(engine, in_stream, out_stream)

    # Assert — banner and capability listing reached the user
    output = out_stream.getvalue()
    assert "AUTON — chat control plane" in output
    assert "echo" in output
    assert "repeats your text back" in output

    # Turns were persisted: user "what can you do" + auton help reply.
    history = engine.session.history()
    assert any(t.role == "user" and t.text == "what can you do" for t in history)
    assert any(t.role == "auton" and "echo" in t.text for t in history)


def test_run_dispatches_to_capability(tmp_path):
    # Arrange
    engine = _engine(tmp_path)
    in_stream = io.StringIO("echo hello\nquit\n")
    out_stream = io.StringIO()

    # Act
    run(engine, in_stream, out_stream)

    # Assert
    assert "echo: echo hello" in out_stream.getvalue()


def test_run_exits_on_quit_without_processing_more(tmp_path):
    # Arrange — line after quit must never be handled
    engine = _engine(tmp_path)
    in_stream = io.StringIO("quit\necho should-not-run\n")
    out_stream = io.StringIO()

    # Act
    run(engine, in_stream, out_stream)

    # Assert
    history = engine.session.history()
    assert all("should-not-run" not in t.text for t in history)


def test_run_exits_cleanly_on_eof(tmp_path):
    # Arrange — no quit line, stream ends (EOF / closed pipe)
    engine = _engine(tmp_path)
    in_stream = io.StringIO("echo bye\n")
    out_stream = io.StringIO()

    # Act / Assert — does not hang or raise
    run(engine, in_stream, out_stream)
    assert "echo: echo bye" in out_stream.getvalue()


def test_run_ignores_blank_lines(tmp_path):
    # Arrange
    engine = _engine(tmp_path)
    in_stream = io.StringIO("\n   \necho x\nquit\n")
    out_stream = io.StringIO()

    # Act
    run(engine, in_stream, out_stream)

    # Assert — blank lines produced no user turns
    history = engine.session.history()
    user_texts = [t.text for t in history if t.role == "user"]
    assert "echo x" in user_texts
    assert "" not in user_texts
