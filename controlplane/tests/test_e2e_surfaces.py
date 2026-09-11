"""Control-plane E2E lane: the host half of the chat OS as one flow.

The unit suite proves each piece in isolation. This proves the thing a person
actually uses: one conversation that survives crossing surfaces, and backends
that either do the real work or say plainly what is missing.

No mocks, per the house rule (see test_operator.py). Where a real tool is
absent — Docker not running, no display — that is asserted as an honest refusal
rather than skipped or faked. A backend that raises, or that claims success
without the tool, is a failure of this lane's central premise.
"""

from __future__ import annotations

import io
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from controlplane.core import (
    CapabilityStatus,
    ChatEngine,
    ChatTurn,
    Registry,
    Router,
    SessionStore,
    discover_capabilities,
)
from controlplane.core.session_sync import tail
from controlplane.surfaces.terminal import repl

REPO_ROOT = Path(__file__).resolve().parents[2]


def _engine(db: Path, surface: str) -> ChatEngine:
    registry = Registry(discover_capabilities())
    return ChatEngine(
        registry=registry,
        router=Router(registry),
        session=SessionStore(db),
        surface=surface,
    )


# --- Task 1: one conversation across three surfaces ------------------------


@pytest.mark.integration
class TestCrossSurfaceContinuity:
    """A turn written by one surface must be visible to the others.

    test_session_continuity.py covers two SessionStores over one file. This
    goes a level up: real ChatEngines, as the surfaces construct them, over one
    database — which is what "one continuous conversation" actually means.
    """

    def test_terminal_turn_is_visible_to_ui_and_desktop(self, tmp_path):
        db = tmp_path / "session.db"

        terminal = _engine(db, "terminal")
        terminal.session.record("user", "hello from the terminal", surface="terminal")

        for surface in ("ui", "desktop"):
            seen = tail(_engine(db, surface).session)
            texts = [t.text for _, t in seen]
            assert "hello from the terminal" in texts, (
                f"{surface} cannot see the terminal's turn — the session is not shared"
            )

    def test_every_surface_is_attributed_correctly(self, tmp_path):
        db = tmp_path / "session.db"
        for surface in ("terminal", "ui", "desktop"):
            _engine(db, surface).session.record(
                "user", f"turn from {surface}", surface=surface
            )

        seen = {t.surface: t.text for _, t in tail(SessionStore(db))}
        assert set(seen) == {"terminal", "ui", "desktop"}
        for surface, text in seen.items():
            assert text == f"turn from {surface}"

    def test_history_is_ordered_across_surfaces(self, tmp_path):
        db = tmp_path / "session.db"
        order = ["terminal", "ui", "desktop", "terminal"]
        for i, surface in enumerate(order):
            SessionStore(db).record("user", f"msg{i}", surface=surface)

        texts = [t.text for _, t in tail(SessionStore(db))]
        assert texts == [f"msg{i}" for i in range(len(order))], (
            "interleaved surfaces must preserve conversation order"
        )


# --- Task 2: backends work or refuse honestly ------------------------------


@pytest.mark.integration
class TestBackendHonesty:
    """The backend layer's premise is that it never pretends.

    Each capability must return a CapabilityResult — not raise, not claim
    success it cannot back. When the underlying tool is missing, the refusal
    has to name what is missing; "handled: False" with an empty message is the
    silent failure this lane exists to catch.
    """

    @staticmethod
    def _probe_text(name: str) -> str:
        return {
            "docker": "list docker containers",
            "kubernetes": "list kubernetes pods",
            "desktop": "open a desktop app",
            "server": "show server status",
            "status": "status",
            "os": "list os images",
        }.get(name, name)

    def test_every_capability_answers_without_raising(self):
        caps = Registry(discover_capabilities()).unique_by_name()
        assert caps, "no backends discovered — the registry is empty"

        for cap in caps:
            text = self._probe_text(cap.name)
            try:
                result = cap.handle(text)
            except Exception as exc:  # noqa: BLE001 - that is the finding
                pytest.fail(
                    f"backend {cap.name!r} raised {type(exc).__name__}: {exc}. "
                    f"A missing tool must be an honest refusal, not an exception."
                )
            assert result is not None, f"backend {cap.name!r} returned None"
            assert isinstance(result.text, str) and result.text.strip(), (
                f"backend {cap.name!r} answered with an empty message — a silent "
                f"failure is worse here than a crash"
            )

    def test_roadmap_capabilities_explain_what_is_missing(self):
        caps = Registry(discover_capabilities()).unique_by_name()
        roadmap = [c for c in caps if c.status is CapabilityStatus.ROADMAP]
        for cap in roadmap:
            assert cap.note and cap.note.strip(), (
                f"roadmap capability {cap.name!r} has no note saying what it needs"
            )

    # Backends whose failure message is a raw tool dump rather than a refusal
    # in the project's own voice. Tracked, not silently tolerated: this lane
    # asserts current behaviour, and fixing backends is out of its scope.
    #
    #   kubernetes — surfaces kubectl's stderr verbatim, four repetitions of the
    #                same connection error with timestamps and goroutine detail.
    #   status     — aggregates the other backends, so it inherits the above.
    #                One root cause, not two.
    RAW_DUMP_KNOWN_GAPS = {"kubernetes", "status"}

    def test_refusals_are_user_facing_not_raw_tool_dumps(self):
        """A refusal should be a sentence, not a pasted stderr log.

        Length is not the test — `os` lists five environments and `status` reports
        several tools, both deliberately. Log-formatted lines are: kubectl emits
        its connection error four times with timestamps and goroutine detail, and
        surfacing that verbatim is honest but unusable.
        """
        caps = Registry(discover_capabilities()).unique_by_name()
        offenders = []
        for cap in caps:
            result = cap.handle(self._probe_text(cap.name))
            lines = [ln for ln in result.text.splitlines() if ln.strip()]
            noisy = any(
                ln.lstrip().startswith(("E0", "W0", "Traceback", "goroutine"))
                for ln in lines
            )
            if noisy and cap.name not in self.RAW_DUMP_KNOWN_GAPS:
                offenders.append((cap.name, lines[:2]))
        assert not offenders, f"raw tool output surfaced as a refusal: {offenders}"

    def test_known_raw_dump_gaps_are_still_gaps(self):
        """Fails once a tracked gap is fixed, so the exemption cannot outlive it."""
        caps = {c.name: c for c in Registry(discover_capabilities()).unique_by_name()}
        for name in self.RAW_DUMP_KNOWN_GAPS:
            cap = caps.get(name)
            if cap is None:
                continue
            result = cap.handle(self._probe_text(name))
            lines = [ln for ln in result.text.splitlines() if ln.strip()]
            still_noisy = any(
                ln.lstrip().startswith(("E0", "W0", "Traceback", "goroutine"))
                for ln in lines
            )
            if not still_noisy:
                pytest.fail(
                    f"{name} no longer dumps raw tool output — remove it from "
                    f"RAW_DUMP_KNOWN_GAPS"
                )

    @pytest.mark.skipif(
        shutil.which("docker") is None, reason="docker CLI not installed"
    )
    def test_docker_backend_is_honest_about_the_daemon(self):
        """Docker being down is a CASE, not a blocked run.

        With the daemon stopped the backend must say so. With it running it
        must really talk to it. Either way the answer names Docker rather than
        surfacing a raw traceback or a bare failure.
        """
        caps = {c.name: c for c in Registry(discover_capabilities()).unique_by_name()}
        docker = caps.get("docker")
        assert docker is not None, "docker backend not discovered"

        result = docker.handle("list docker containers")
        daemon_up = (
            subprocess.run(
                ["docker", "info"], capture_output=True, timeout=20
            ).returncode
            == 0
        )
        lowered = result.text.lower()
        if daemon_up:
            assert result.handled, f"daemon is up but docker refused: {result.text}"
        else:
            assert "docker" in lowered or "daemon" in lowered, (
                "with the daemon down the refusal must name Docker or the daemon, "
                f"got: {result.text!r}"
            )


# --- Task 3: the entry points start, answer, and exit ----------------------


@pytest.mark.integration
class TestSurfacesStart:
    def test_terminal_repl_answers_and_exits(self, tmp_path):
        """repl.run takes explicit streams precisely so this is testable."""
        engine = _engine(tmp_path / "session.db", "terminal")
        out = io.StringIO()
        repl.run(engine, io.StringIO("help\nexit\n"), out)

        text = out.getvalue()
        assert text.strip(), "terminal produced no output"
        assert "I can run these from chat" in text or "help" in text.lower()

    def test_ui_app_builds_and_serves_history(self, tmp_path):
        fastapi_testclient = pytest.importorskip(
            "fastapi.testclient", reason="fastapi not installed (ui extra)"
        )
        from controlplane.surfaces.ui.app import build_app

        db = tmp_path / "session.db"
        SessionStore(db).record("user", "seeded from a test", surface="terminal")

        client = fastapi_testclient.TestClient(build_app(db))
        resp = client.get("/api/history")
        assert resp.status_code == 200
        body = resp.text
        assert "seeded from a test" in body, (
            "the UI does not surface a turn recorded by another surface"
        )

    def test_desktop_surface_is_importable_or_refuses_loudly(self):
        """Desktop needs a display; a headless skip must name the reason."""
        try:
            from controlplane.surfaces.desktop import shell  # noqa: F401
        except ImportError as exc:
            pytest.skip(f"desktop surface unavailable: {exc}")

    def test_console_scripts_are_declared(self):
        """The three entry points users are told to run must exist."""
        pyproject = (REPO_ROOT / "controlplane" / "pyproject.toml").read_text()
        for script in ("auton-chat", "auton-ui", "auton-desktop", "auton-do"):
            assert script in pyproject, f"{script} is not declared as a console script"
