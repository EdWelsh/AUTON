"""macOS adapter: pure argv builders for launch/close/list.

Launch uses ``open -a <App>``; close/list use ``osascript`` (AppleScript) which
addresses apps by name the same way ``open -a`` does. Every function here is a
pure string-assembly helper so it can be unit-tested without a real machine.
"""

from __future__ import annotations


def launch_argv(app: str) -> list[str]:
    """``open -a <App>`` — the canonical macOS app launcher."""
    return ["open", "-a", app]


def close_argv(app: str) -> list[str]:
    """Politely quit an app by name via AppleScript."""
    script = f'tell application "{app}" to quit'
    return ["osascript", "-e", script]


def list_argv() -> list[str]:
    """List visible (non-background) application process names via AppleScript."""
    script = (
        'tell application "System Events" to get name of '
        "(every process whose background only is false)"
    )
    return ["osascript", "-e", script]
