"""Tests for the server/process backend (Unit 4).

No mocks: the supervisor launches REAL host processes via subprocess and we
assert liveness/listing/stop against them. Utterance parsing is pure and unit
tested separately.
"""

from __future__ import annotations

import sys
import time

import pytest

from controlplane.backends.server.plugin import get_capabilities
from controlplane.backends.server.supervisor import (
    ParsedCommand,
    ServerRecord,
    Supervisor,
    parse_utterance,
)
from controlplane.core import Registry


# ---------------------------------------------------------------------------
# Pure utterance parsing
# ---------------------------------------------------------------------------


def test_parse_start_extracts_command_after_as_a_service():
    parsed = parse_utterance("run python3 -m http.server 8000 as a service")
    assert parsed.action == "start"
    assert parsed.command == "python3 -m http.server 8000"
    assert parsed.port == 8000


def test_parse_start_web_server_uses_default_command():
    parsed = parse_utterance("start a web server")
    assert parsed.action == "start"
    assert parsed.command  # a non-empty default command
    assert parsed.port is not None


def test_parse_start_extracts_explicit_name():
    parsed = parse_utterance("start a server named hello running sleep 30")
    assert parsed.action == "start"
    assert parsed.name == "hello"
    assert "sleep 30" in parsed.command


def test_parse_stop_extracts_name():
    parsed = parse_utterance("stop the server hello")
    assert parsed.action == "stop"
    assert parsed.name == "hello"


def test_parse_list_action():
    parsed = parse_utterance("what servers are running")
    assert parsed.action == "list"


def test_parse_returns_parsed_command_type():
    assert isinstance(parse_utterance("start a web server"), ParsedCommand)


# ---------------------------------------------------------------------------
# Real process lifecycle (no mocks)
# ---------------------------------------------------------------------------

SLEEP_CMD = f'{sys.executable} -c "import time; time.sleep(30)"'


@pytest.fixture()
def supervisor(tmp_path):
    sup = Supervisor(state_path=tmp_path / "servers.json")
    yield sup
    sup.stop_all()


def _wait_dead(sup: Supervisor, pid: int, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while sup.is_alive(pid) and time.time() < deadline:
        time.sleep(0.05)


def test_start_lists_then_stop_real_process(supervisor):
    rec = supervisor.start(command=SLEEP_CMD, name="sleeper")

    assert isinstance(rec, ServerRecord)
    assert rec.pid > 0
    assert supervisor.is_alive(rec.pid)

    running = supervisor.list_running()
    assert any(r.name == "sleeper" for r in running)

    assert supervisor.stop("sleeper") is True

    _wait_dead(supervisor, rec.pid)
    assert not supervisor.is_alive(rec.pid)
    assert all(r.name != "sleeper" for r in supervisor.list_running())


def test_state_persists_across_instances(tmp_path):
    state = tmp_path / "servers.json"
    sup1 = Supervisor(state_path=state)
    sup1.start(command=SLEEP_CMD, name="persistent")
    try:
        # A fresh supervisor reading the same state file sees the live process.
        sup2 = Supervisor(state_path=state)
        names = [r.name for r in sup2.list_running()]
        assert "persistent" in names
    finally:
        sup1.stop_all()


def test_list_reconciles_dead_processes(tmp_path):
    state = tmp_path / "servers.json"
    sup = Supervisor(state_path=state)
    rec = sup.start(command=SLEEP_CMD, name="doomed")
    sup.stop("doomed")
    _wait_dead(sup, rec.pid)

    # A new supervisor must not report the dead pid as running.
    fresh = Supervisor(state_path=state)
    assert all(r.name != "doomed" for r in fresh.list_running())


def test_duplicate_name_is_rejected(supervisor):
    supervisor.start(command=SLEEP_CMD, name="dup")
    with pytest.raises(ValueError):
        supervisor.start(command=SLEEP_CMD, name="dup")


def test_stop_unknown_name_returns_false(supervisor):
    assert supervisor.stop("nope") is False


# ---------------------------------------------------------------------------
# Capability + routing
# ---------------------------------------------------------------------------


def test_get_capabilities_exposes_working_server():
    caps = get_capabilities()
    assert len(caps) == 1
    cap = caps[0]
    assert cap.name == "server"
    assert cap.status.value == "working"
    assert cap.handler is not None


def test_routing_reaches_server_capability():
    cap = Registry().match("start a web server")
    assert cap is not None
    assert cap.name == "server"


def test_handler_start_list_stop_round_trip(tmp_path, monkeypatch):
    from controlplane.backends.server import plugin as server_plugin

    sup = Supervisor(state_path=tmp_path / "servers.json")
    monkeypatch.setattr(server_plugin, "_SUPERVISOR", sup)

    handler = get_capabilities()[0].handler
    assert handler is not None

    start_cmd = (
        f'run {sys.executable} -c "import time; time.sleep(30)" '
        f"as a service named cli"
    )
    try:
        start_res = handler(start_cmd)
        assert start_res.handled
        assert start_res.error is None

        list_res = handler("what servers are running")
        assert "cli" in list_res.text

        stop_res = handler("stop the server cli")
        assert stop_res.handled
        assert stop_res.error is None
    finally:
        sup.stop_all()
