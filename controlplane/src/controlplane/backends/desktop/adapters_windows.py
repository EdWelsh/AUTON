"""Windows adapter: pure argv builders for launch/close/list.

Launch uses ``start "" <app>`` (the empty string is the window title argument
``start`` requires before the target). Close uses ``taskkill``; list uses
``tasklist``. Pure helpers; the real run on Windows goes through ``cmd /c``.
"""

from __future__ import annotations


def launch_argv(app: str) -> list[str]:
    """``start "" <app>`` — the empty title arg keeps ``start`` from eating ``app``."""
    return ["start", "", app]


def close_argv(image: str) -> list[str]:
    """``taskkill /IM <image> /F`` — force-close by image name (e.g. notepad.exe)."""
    return ["taskkill", "/IM", image, "/F"]


def list_argv() -> list[str]:
    """List running image names."""
    return ["tasklist"]
