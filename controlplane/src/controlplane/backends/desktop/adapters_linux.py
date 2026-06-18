"""Linux adapter: pure argv builders for launch/close/list.

Launch prefers ``gtk-launch <desktop-id>`` (proper .desktop activation) and falls
back to ``xdg-open <app>``. Close uses ``pkill -f``; list prefers ``wmctrl -l``
(open windows) and falls back to ``ps``. Pure helpers, unit-tested off-machine.
"""

from __future__ import annotations


def launch_argv(app: str, has_gtk_launch: bool) -> list[str]:
    """``gtk-launch <app>`` when available, else ``xdg-open <app>``."""
    if has_gtk_launch:
        return ["gtk-launch", app]
    return ["xdg-open", app]


def close_argv(app: str) -> list[str]:
    """Terminate processes whose command line matches ``app``."""
    return ["pkill", "-f", app]


def list_argv(has_wmctrl: bool = True) -> list[str]:
    """List open windows via ``wmctrl -l``, falling back to ``ps``."""
    if has_wmctrl:
        return ["wmctrl", "-l"]
    return ["ps", "-eo", "comm"]
