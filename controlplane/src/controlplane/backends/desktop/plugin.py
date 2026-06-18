"""Desktop backend plugin: exposes the WORKING ``desktop`` capability.

The registry calls :func:`get_capabilities` at discovery time. A single shared
:class:`Launcher` instance backs the handler so app-tracking state ("what apps
are open") persists across utterances within a running session.
"""

from __future__ import annotations

from controlplane.core import Capability, CapabilityResult, CapabilityStatus

from .launcher import Launcher

# One launcher per process keeps the "open apps" set consistent across turns.
_LAUNCHER = Launcher()


def _handle(text: str) -> CapabilityResult:
    return _LAUNCHER.handle(text)


def get_capabilities() -> list[Capability]:
    return [
        Capability(
            name="desktop",
            keywords=(
                "launch",
                "open app",
                "open the",
                "close app",
                "close ",
                "quit app",
                "quit ",
                "apps open",
                "what apps are open",
                "list apps",
            ),
            status=CapabilityStatus.WORKING,
            note="Launch, close, and list desktop apps (macOS/Linux/Windows).",
            handler=_handle,
        )
    ]
