"""Cross-platform desktop app launcher.

Parses a natural-language utterance ("launch firefox", "close safari", "what apps
are open") into an :class:`Action`, builds the per-OS argv via the right adapter
(selected from ``sys.platform``), runs the real tool, and tracks which apps this
session launched so "what apps are open" can report them.

The argv building lives in the ``adapters_*`` modules as pure functions; this
module wires them together and runs subprocesses. The subprocess runner is
injectable so tests can drive tracking logic without spawning real processes —
the real-launch tests use the default runner with a harmless app, never a mock.
"""

from __future__ import annotations

import enum
import shutil
import subprocess  # noqa: S404 - launching apps is the whole point of this backend
import sys
from dataclasses import dataclass
from typing import Callable

from controlplane.core import CapabilityResult

from . import adapters_linux, adapters_macos, adapters_windows

# (returncode, stdout, stderr)
Runner = Callable[[list[str]], "tuple[int, str, str]"]

_LAUNCH_TIMEOUT_S = 20
_CLOSE_TIMEOUT_S = 20
_LIST_TIMEOUT_S = 20

# Stripped from "open the calculator" / "launch the firefox" etc.
_LEADING_NOISE = ("the ", "app ", "application ")


class Action(enum.Enum):
    """What the user wants to do with a desktop app."""

    LAUNCH = "launch"
    CLOSE = "close"
    LIST = "list"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Command:
    """A parsed desktop request: an action plus an (optional) app name."""

    action: Action
    app: str


# Order matters: list/close keywords are checked before launch so that "what apps
# are open" is not mis-read as a launch, and "close"/"quit" win over "open".
_LIST_KEYWORDS = ("what apps are open", "apps open", "list apps", "which apps")
_CLOSE_KEYWORDS = ("close", "quit", "kill")
_LAUNCH_KEYWORDS = ("launch", "open app", "open the", "open ", "start ", "run ")


def _strip_noise(name: str) -> str:
    name = name.strip()
    lowered = name.lower()
    for noise in _LEADING_NOISE:
        if lowered.startswith(noise):
            return name[len(noise):].strip()
    return name


def parse_command(text: str) -> Command:
    """Turn an utterance into a :class:`Command` (pure, deterministic)."""
    lowered = text.lower().strip()

    for kw in _LIST_KEYWORDS:
        if kw in lowered:
            return Command(Action.LIST, "")

    for kw in _CLOSE_KEYWORDS:
        if kw in lowered:
            app = _after_keyword(text, kw)
            return Command(Action.CLOSE, _strip_noise(app))

    for kw in _LAUNCH_KEYWORDS:
        idx = lowered.find(kw)
        if idx != -1:
            app = text[idx + len(kw):]
            return Command(Action.LAUNCH, _strip_noise(app))

    return Command(Action.UNKNOWN, "")


def _after_keyword(text: str, keyword: str) -> str:
    """Return the substring of ``text`` following the first match of ``keyword``."""
    idx = text.lower().find(keyword)
    if idx == -1:
        return ""
    return text[idx + len(keyword):]


def _default_runner(argv: list[str]) -> tuple[int, str, str]:
    """Run ``argv`` and capture output. On Windows, ``start`` is a shell builtin."""
    if sys.platform.startswith("win"):
        argv = ["cmd", "/c", *argv]
    proc = subprocess.run(  # noqa: S603 - argv is built from vetted adapters
        argv,
        capture_output=True,
        text=True,
        timeout=_LAUNCH_TIMEOUT_S,
    )
    return proc.returncode, proc.stdout, proc.stderr


class Launcher:
    """Routes desktop commands to the current OS's adapter and tracks open apps."""

    def __init__(self, runner: Runner | None = None) -> None:
        self._runner: Runner = runner or _default_runner
        self._open_apps: list[str] = []

    # -- public entrypoint --------------------------------------------------- #

    def handle(self, text: str) -> CapabilityResult:
        cmd = parse_command(text)
        if cmd.action is Action.LAUNCH:
            return self._launch(cmd.app)
        if cmd.action is Action.CLOSE:
            return self._close(cmd.app)
        if cmd.action is Action.LIST:
            return self._list()
        return CapabilityResult.fail(
            "Unrecognized desktop command",
            "Try 'launch <app>', 'close <app>', or 'what apps are open'.",
        )

    # -- actions ------------------------------------------------------------- #

    def _launch(self, app: str) -> CapabilityResult:
        if not app:
            return CapabilityResult.fail(
                "No app name given", "Which app should I launch? e.g. 'launch firefox'."
            )
        argv = self._launch_argv(app)
        code, _out, err = self._run(argv)
        if code != 0:
            return CapabilityResult.fail(
                f"Failed to launch {app}: {err.strip() or f'exit {code}'}",
                f"Couldn't launch {app}.",
            )
        self._track(app)
        return CapabilityResult.ok(f"Launched {app}.", app=app, action="launch")

    def _close(self, app: str) -> CapabilityResult:
        if not app:
            return CapabilityResult.fail(
                "No app name given", "Which app should I close?"
            )
        argv = self._close_argv(app)
        code, _out, err = self._run(argv)
        self._untrack(app)
        if code != 0:
            return CapabilityResult.fail(
                f"Failed to close {app}: {err.strip() or f'exit {code}'}",
                f"Couldn't close {app} (it may not have been running).",
            )
        return CapabilityResult.ok(f"Closed {app}.", app=app, action="close")

    def _list(self) -> CapabilityResult:
        tracked = list(self._open_apps)
        if not tracked:
            text = "No apps launched from this session yet."
        else:
            text = "Apps launched this session: " + ", ".join(tracked)
        return CapabilityResult.ok(text, apps=tracked, action="list")

    # -- adapter selection (pure argv) --------------------------------------- #

    def _launch_argv(self, app: str) -> list[str]:
        if sys.platform == "darwin":
            return adapters_macos.launch_argv(app)
        if sys.platform.startswith("win"):
            return adapters_windows.launch_argv(app)
        return adapters_linux.launch_argv(
            app, has_gtk_launch=shutil.which("gtk-launch") is not None
        )

    def _close_argv(self, app: str) -> list[str]:
        if sys.platform == "darwin":
            return adapters_macos.close_argv(app)
        if sys.platform.startswith("win"):
            return adapters_windows.close_argv(app)
        return adapters_linux.close_argv(app)

    # -- tracking ------------------------------------------------------------ #

    def _track(self, app: str) -> None:
        if app.lower() not in {a.lower() for a in self._open_apps}:
            self._open_apps.append(app)

    def _untrack(self, app: str) -> None:
        self._open_apps = [a for a in self._open_apps if a.lower() != app.lower()]

    # -- subprocess ---------------------------------------------------------- #

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        try:
            return self._runner(argv)
        except FileNotFoundError as exc:
            return 127, "", f"command not found: {exc}"
        except subprocess.TimeoutExpired:
            # A launcher that detaches the GUI app can still hang the parent; a
            # timeout means the app most likely started, so treat it as success.
            return 0, "", ""
        except OSError as exc:  # noqa: BLE001 - surface as a failed run, never crash chat
            return 1, "", str(exc)
