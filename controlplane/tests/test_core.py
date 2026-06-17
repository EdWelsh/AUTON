"""Foundation contract tests (Unit 0).

These pin the frozen interface that all backend/surface units build against:
Capability match/handle, Registry discovery & dedup, Router fallback, SQLite
session round-trip + cross-connection visibility, and ChatEngine turn recording.
"""

from __future__ import annotations

import pytest

from controlplane.core import (
    Capability,
    CapabilityResult,
    CapabilityStatus,
    ChatEngine,
    ChatTurn,
    Registry,
    Router,
    SessionStore,
)


def _echo(text: str) -> CapabilityResult:
    return CapabilityResult.ok(f"ran: {text}", echoed=text)


def working_cap(name="docker", keywords=("docker", "container")) -> Capability:
    return Capability(
        name=name,
        keywords=keywords,
        status=CapabilityStatus.WORKING,
        note="real docker",
        handler=_echo,
    )


def roadmap_cap(name="kubernetes", keywords=("k8s", "kubernetes")) -> Capability:
    return Capability(
        name=name,
        keywords=keywords,
        status=CapabilityStatus.ROADMAP,
        note="needs a cluster",
    )


# --- Capability -------------------------------------------------------------

def test_capability_matches_any_keyword_case_insensitive():
    cap = working_cap()
    assert cap.matches("run nginx in DOCKER")
    assert cap.matches("list my containers")
    assert not cap.matches("launch firefox")


def test_capability_normalizes_string_keyword():
    cap = Capability("x", "solo", CapabilityStatus.ROADMAP, "n")
    assert cap.keywords == ("solo",)


def test_working_capability_requires_handler():
    with pytest.raises(ValueError):
        Capability("bad", ("k",), CapabilityStatus.WORKING, "n", handler=None)


def test_working_capability_runs_handler():
    res = working_cap().handle("run nginx in docker")
    assert res.handled is True
    assert res.error is None
    assert res.data["echoed"] == "run nginx in docker"


def test_roadmap_capability_explains_note():
    res = roadmap_cap().handle("deploy to kubernetes")
    assert res.handled is True
    assert "roadmap" in res.text.lower()
    assert res.data["status"] == "roadmap"


# --- Registry ---------------------------------------------------------------

def test_registry_match_returns_first_matching():
    reg = Registry([working_cap(), roadmap_cap()])
    assert reg.match("scale my k8s deploy").name == "kubernetes"
    assert reg.match("docker ps").name == "docker"
    assert reg.match("nothing here") is None


def test_registry_unique_by_name_dedups():
    a = working_cap(name="docker", keywords=("docker",))
    b = working_cap(name="docker", keywords=("container",))
    c = roadmap_cap()
    reg = Registry([a, b, c])
    names = [cap.name for cap in reg.unique_by_name()]
    assert names == ["docker", "kubernetes"]


def test_registry_discovers_no_backends_gracefully():
    # No backend plugins are installed in the foundation; discovery must not raise.
    reg = Registry()
    assert isinstance(reg.capabilities, list)


# --- Router -----------------------------------------------------------------

def test_router_dispatches_to_capability():
    reg = Registry([working_cap()])
    res = Router(reg).route("docker ps")
    assert res.handled and res.text.startswith("ran:")


def test_router_unhandled_when_nothing_matches():
    res = Router(Registry([working_cap()])).route("make me a sandwich")
    assert res.handled is False
    assert "what can you do" in res.text.lower()


def test_router_uses_intent_resolver_fallback():
    reg = Registry([working_cap()])
    called = {}

    def resolver(text, registry):
        called["text"] = text
        return registry.capabilities[0]

    res = Router(reg, intent_resolver=resolver).route("please spin that up")
    assert res.handled and called["text"] == "please spin that up"


# --- SessionStore -----------------------------------------------------------

def test_session_round_trip(tmp_path):
    store = SessionStore(tmp_path / "s.db")
    store.append(ChatTurn(role="user", text="hello", surface="terminal"))
    store.record("auton", "hi there", surface="terminal", handled=True)
    hist = store.history()
    assert [t.role for t in hist] == ["user", "auton"]
    assert hist[0].text == "hello"
    assert hist[1].data["handled"] is True


def test_session_history_limit(tmp_path):
    store = SessionStore(tmp_path / "s.db")
    for i in range(5):
        store.record("user", f"msg{i}")
    assert [t.text for t in store.history(limit=2)] == ["msg3", "msg4"]


def test_session_visible_across_connections(tmp_path):
    """Cross-surface continuity: a second store on the same db sees the turns."""
    db = tmp_path / "shared.db"
    terminal = SessionStore(db)
    terminal.record("user", "from terminal", surface="terminal")

    ui = SessionStore(db)  # simulates the UI surface opening the same session
    texts = [t.text for t in ui.history()]
    assert "from terminal" in texts


# --- ChatEngine -------------------------------------------------------------

def test_chat_engine_records_user_and_reply(tmp_path):
    reg = Registry([working_cap()])
    engine = ChatEngine(
        registry=reg,
        router=Router(reg),
        session=SessionStore(tmp_path / "s.db"),
        surface="terminal",
    )
    res = engine.handle("docker ps")
    assert res.handled
    roles = [t.role for t in engine.session.history()]
    assert roles == ["user", "auton"]


def test_chat_engine_help_lists_capabilities(tmp_path):
    reg = Registry([working_cap(), roadmap_cap()])
    engine = ChatEngine(registry=reg, session=SessionStore(tmp_path / "s.db"))
    res = engine.handle("what can you do")
    assert "docker" in res.text and "kubernetes" in res.text
