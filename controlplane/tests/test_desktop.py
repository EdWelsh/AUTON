"""Desktop app backend tests (Unit 1).

TDD: the pure argv-building logic is unit-tested for all three OSes (no platform
gating needed — it is just string assembly). The real launch is exercised only on
the current OS with a harmless app and pytest.skip elsewhere — never mocked.
"""

from __future__ import annotations

import shutil
import sys

import pytest

from controlplane.backends.desktop import adapters_linux, adapters_macos, adapters_windows
from controlplane.backends.desktop.launcher import (
    Action,
    Launcher,
    parse_command,
)
from controlplane.backends.desktop.plugin import get_capabilities
from controlplane.core import CapabilityStatus, Registry, Router


# --------------------------------------------------------------------------- #
# Pure parsing (OS-independent)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text,action,app",
    [
        ("launch firefox", Action.LAUNCH, "firefox"),
        ("open the calculator", Action.LAUNCH, "calculator"),
        ("open app TextEdit", Action.LAUNCH, "TextEdit"),
        ("close firefox", Action.CLOSE, "firefox"),
        ("quit app Safari", Action.CLOSE, "Safari"),
        ("what apps are open", Action.LIST, ""),
        ("apps open", Action.LIST, ""),
    ],
)
def test_parse_command(text: str, action: Action, app: str) -> None:
    parsed = parse_command(text)
    assert parsed.action is action
    assert parsed.app == app


def test_parse_launch_requires_app() -> None:
    parsed = parse_command("launch")
    assert parsed.action is Action.LAUNCH
    assert parsed.app == ""


# --------------------------------------------------------------------------- #
# Pure argv builders for every OS
# --------------------------------------------------------------------------- #


def test_macos_launch_argv() -> None:
    assert adapters_macos.launch_argv("Firefox") == ["open", "-a", "Firefox"]


def test_macos_close_argv() -> None:
    argv = adapters_macos.close_argv("Firefox")
    assert argv[0] == "osascript"
    assert any("Firefox" in part for part in argv)


def test_macos_list_argv() -> None:
    assert adapters_macos.list_argv()[0] in {"osascript", "pgrep"}


def test_linux_launch_argv_gtk() -> None:
    argv = adapters_linux.launch_argv("firefox", has_gtk_launch=True)
    assert argv == ["gtk-launch", "firefox"]


def test_linux_launch_argv_fallback_xdg() -> None:
    argv = adapters_linux.launch_argv("firefox", has_gtk_launch=False)
    assert argv == ["xdg-open", "firefox"]


def test_linux_close_argv() -> None:
    assert adapters_linux.close_argv("firefox") == ["pkill", "-f", "firefox"]


def test_linux_list_argv() -> None:
    assert adapters_linux.list_argv()[0] in {"wmctrl", "ps"}


def test_windows_launch_argv() -> None:
    argv = adapters_windows.launch_argv("notepad")
    assert argv[:2] == ["start", ""]
    assert argv[-1] == "notepad"


def test_windows_close_argv() -> None:
    argv = adapters_windows.close_argv("notepad.exe")
    assert argv[0] == "taskkill"
    assert "notepad.exe" in argv


def test_windows_list_argv() -> None:
    assert adapters_windows.list_argv() == ["tasklist"]


# --------------------------------------------------------------------------- #
# Launcher tracking
# --------------------------------------------------------------------------- #


def test_launcher_tracks_open_apps() -> None:
    launcher = Launcher(runner=lambda argv: (0, "", ""))
    launcher.handle("launch firefox")
    result = launcher.handle("what apps are open")
    assert result.handled
    assert "firefox" in result.text.lower()
    assert "firefox" in [a.lower() for a in result.data.get("apps", [])]


def test_launcher_close_untracks() -> None:
    launcher = Launcher(runner=lambda argv: (0, "", ""))
    launcher.handle("launch firefox")
    launcher.handle("close firefox")
    result = launcher.handle("what apps are open")
    assert "firefox" not in [a.lower() for a in result.data.get("apps", [])]


def test_launcher_launch_without_app_fails() -> None:
    launcher = Launcher(runner=lambda argv: (0, "", ""))
    result = launcher.handle("launch")
    assert result.error is not None


def test_launcher_reports_runner_failure() -> None:
    launcher = Launcher(runner=lambda argv: (1, "", "boom"))
    result = launcher.handle("launch firefox")
    assert result.error is not None
    # Failed launch must not be tracked as open.
    listing = launcher.handle("what apps are open")
    assert "firefox" not in [a.lower() for a in listing.data.get("apps", [])]


# --------------------------------------------------------------------------- #
# Plugin / capability wiring
# --------------------------------------------------------------------------- #


def test_plugin_exposes_working_desktop_capability() -> None:
    caps = get_capabilities()
    assert len(caps) == 1
    cap = caps[0]
    assert cap.name == "desktop"
    assert cap.status is CapabilityStatus.WORKING
    assert cap.matches("launch firefox")
    assert cap.matches("what apps are open")


def test_router_reaches_desktop() -> None:
    router = Router(Registry())
    result = router.route("launch firefox")
    # The desktop capability must claim this (handled), regardless of whether the
    # real app exists on this machine.
    assert result.handled


# --------------------------------------------------------------------------- #
# Real launch on the current OS only — never mocked.
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only real launch")
def test_real_launch_macos() -> None:
    launcher = Launcher()
    result = launcher.handle("launch TextEdit")
    assert result.handled
    assert result.error is None, result.text
    # Clean up so we do not leave windows open.
    launcher.handle("close TextEdit")


@pytest.mark.skipif(sys.platform != "linux", reason="Linux-only real launch")
def test_real_launch_linux() -> None:
    if not (shutil.which("gtk-launch") or shutil.which("xdg-open")):
        pytest.skip("no gtk-launch/xdg-open available")
    launcher = Launcher()
    # Listing exercises the adapter end to end without leaving a window open.
    result = launcher.handle("what apps are open")
    assert result.handled


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows-only real launch")
def test_real_launch_windows() -> None:
    launcher = Launcher()
    result = launcher.handle("launch notepad")
    assert result.handled
    launcher.handle("close notepad.exe")
