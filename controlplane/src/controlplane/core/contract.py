"""The frozen control-plane contract.

This module defines the stable interface every backend and surface builds
against. Keep it small and additive: backends supply :class:`Capability`
instances; the router dispatches an utterance to the first capability that
matches and returns a :class:`CapabilityResult`.

Mirrors ``kernels/x86_64/kernel/slm/roles.c`` (``capability_t``: keyword, name,
status, note, action) so the host plane and the booted kernel tell one story.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class CapabilityStatus(str, Enum):
    """Whether a capability actually runs today or is a documented roadmap stub."""

    WORKING = "working"
    ROADMAP = "roadmap"


@dataclass(frozen=True)
class CapabilityResult:
    """Outcome of routing one chat utterance.

    Immutable by design (see repo coding-style: never mutate, return new copies).
    Use the classmethod constructors rather than building by hand.
    """

    handled: bool
    text: str = ""
    data: dict = field(default_factory=dict)
    error: str | None = None

    @classmethod
    def ok(cls, text: str, **data: object) -> "CapabilityResult":
        """A capability handled the utterance successfully."""
        return cls(handled=True, text=text, data=dict(data))

    @classmethod
    def unhandled(cls, text: str = "") -> "CapabilityResult":
        """No capability claimed this utterance."""
        return cls(handled=False, text=text)

    @classmethod
    def fail(cls, error: str, text: str = "") -> "CapabilityResult":
        """A capability matched but its real action failed."""
        return cls(handled=True, text=text or error, error=error)


# A handler receives the full utterance text and returns a result. Backends parse
# their own sub-commands from the text (e.g. "stop nginx" -> docker stop nginx),
# exactly like roles.c actions, but with the text passed in.
CapabilityHandler = Callable[[str], CapabilityResult]


@dataclass
class Capability:
    """A single thing the control plane can do, triggered by natural language.

    Attributes
    ----------
    name:     display name, deduped in listings (e.g. "docker").
    keywords: lowercase trigger substrings; ``matches`` is true if any appears.
    status:   WORKING (runs ``handler``) or ROADMAP (explains the note).
    note:     one line on what it does / what it still needs.
    handler:  the real action; required for WORKING, ignored for ROADMAP.
    """

    name: str
    keywords: tuple[str, ...]
    status: CapabilityStatus
    note: str
    handler: CapabilityHandler | None = None

    def __post_init__(self) -> None:
        if isinstance(self.keywords, str):
            object.__setattr__(self, "keywords", (self.keywords,))
        else:
            object.__setattr__(self, "keywords", tuple(self.keywords))
        if self.status is CapabilityStatus.WORKING and self.handler is None:
            raise ValueError(
                f"WORKING capability {self.name!r} must provide a handler"
            )

    def matches(self, text: str) -> bool:
        """Deterministic keyword match (mirrors roles.c ``match`` / ``ks_contains``)."""
        t = text.lower()
        return any(k in t for k in self.keywords)

    def handle(self, text: str) -> CapabilityResult:
        """Run the capability, or explain the roadmap note if it is a stub."""
        if self.status is CapabilityStatus.ROADMAP or self.handler is None:
            return CapabilityResult.ok(
                f"'{self.name}': roadmap — {self.note}",
                status="roadmap",
                capability=self.name,
            )
        return self.handler(text)


@dataclass(frozen=True)
class ChatTurn:
    """One turn in the persistent, cross-surface chat session."""

    role: str  # "user" | "auton"
    text: str
    surface: str = "terminal"  # "terminal" | "ui" | "desktop"
    ts: float = field(default_factory=time.time)
    data: dict = field(default_factory=dict)
