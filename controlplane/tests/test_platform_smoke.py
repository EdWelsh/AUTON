"""Per-surface smoke tests, run on every host the CI matrix covers (C1).

macOS, Linux and Windows each get the same three checks: the terminal surface
answers on a pipe, the UI surface serves HTTP from a real process, and the
desktop launcher's runner really executes a process on this OS.

CI runners have no interactive desktop, so nothing here asserts that a window
appeared: it asserts on the **process**, which is what a headless runner can
honestly tell us. A skip always names what was missing; a surface that is
simply broken on a host fails.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from controlplane.backends.desktop.launcher import _default_runner

REPO = Path(__file__).resolve().parents[1]
TIMEOUT = 90
IS_WINDOWS = sys.platform.startswith("win")


def _env() -> dict[str, str]:
    """The child sees this checkout's package, whether or not it is installed."""
    env = dict(os.environ)
    src = str(REPO / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_terminal_surface_answers_on_a_pipe():
    """`auton-chat` reads stdin and answers: the surface every host must have."""
    proc = subprocess.run(
        [sys.executable, "-m", "controlplane.surfaces.terminal.repl"],
        input="help\nquit\n", capture_output=True, text=True, timeout=TIMEOUT, env=_env(),
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip(), "the terminal surface printed nothing"


def test_ui_surface_serves_http_from_a_real_process():
    pytest.importorskip("uvicorn", reason="the ui extra is not installed")
    pytest.importorskip("fastapi", reason="the ui extra is not installed")
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "controlplane.surfaces.ui.app", "--port", str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=_env(),
    )
    try:
        body, last = None, None
        for _ in range(TIMEOUT):
            if proc.poll() is not None:
                pytest.fail(f"the ui surface exited: {proc.communicate()[0][-2000:]}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as r:
                    body = r.read()
                    break
            except (urllib.error.URLError, ConnectionError, OSError) as exc:  # not up yet
                last = exc
                time.sleep(1)
        assert body is not None, f"the ui surface never answered on {port}: {last}"
        assert body.strip(), "the ui surface served an empty page"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_the_desktop_runner_executes_a_process_on_this_os():
    """The launcher's own runner, on this OS, with a harmless argv.

    Not a window: a CI runner has no desktop session. This covers the part a
    headless host can prove — that `_default_runner` builds and runs a real
    process (on Windows through `cmd /c`, where `start` is a shell builtin).
    """
    # `_default_runner` adds `cmd /c` itself on Windows, where echo is a builtin.
    code, out, err = _default_runner(["echo", "auton"])
    assert code == 0, f"{err.strip()} (exit {code})"
    assert "auton" in out.lower()
