"""Tests for the desktop install surface (Unit 7).

These run headless: the pure ``build_window_config`` helper is exercised
directly, while anything that imports ``webview`` or opens a real window is
guarded by ``importorskip`` plus a display check. We never mock pywebview.
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest


def _has_display() -> bool:
    """True only when a GUI display is plausibly available.

    pywebview needs a real display (X11/Wayland on Linux, Aqua on macOS,
    Win32 on Windows). On headless CI there is none, so window-opening tests
    must skip rather than crash.
    """
    if os.name == "nt":
        return True
    if sys.platform == "darwin":
        # macOS has a window server unless explicitly headless.
        return os.environ.get("CI", "").lower() not in ("1", "true")
    # Linux / other X11-style platforms.
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def test_shell_imports_without_ui_extra() -> None:
    """The module must import even when the ``ui`` extra is absent.

    All UI/webview dependencies are imported lazily inside functions, so a bare
    ``import`` of the shell never pulls in fastapi/uvicorn/pywebview.
    """
    module = importlib.import_module("controlplane.surfaces.desktop.shell")
    assert hasattr(module, "build_window_config")
    assert hasattr(module, "main")


def test_build_window_config_shape() -> None:
    from controlplane.surfaces.desktop.shell import build_window_config

    cfg = build_window_config(port=8731, title="AUTON")

    assert cfg["url"] == "http://127.0.0.1:8731"
    assert cfg["title"] == "AUTON"
    assert isinstance(cfg["size"], tuple)
    assert len(cfg["size"]) == 2
    width, height = cfg["size"]
    assert width > 0 and height > 0


def test_build_window_config_defaults() -> None:
    from controlplane.surfaces.desktop.shell import build_window_config

    cfg = build_window_config(port=5000)

    assert cfg["url"] == "http://127.0.0.1:5000"
    assert cfg["title"]  # non-empty default title


def test_build_window_config_rejects_bad_port() -> None:
    from controlplane.surfaces.desktop.shell import build_window_config

    for bad in (0, -1, 70000):
        with pytest.raises(ValueError):
            build_window_config(port=bad)


@pytest.mark.skipif(not _has_display(), reason="no GUI display available")
def test_webview_importable_when_display_present() -> None:
    # Only assert the dependency is wired when we could actually open a window.
    pytest.importorskip("webview")
