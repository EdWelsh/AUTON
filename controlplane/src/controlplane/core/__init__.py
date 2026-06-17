"""Frozen control-plane contract and core machinery.

Everything a backend or surface needs is re-exported here so call sites import
from a single stable location: ``from controlplane.core import Capability, ...``.
"""

from __future__ import annotations

from .chat import ChatEngine
from .contract import (
    Capability,
    CapabilityResult,
    CapabilityStatus,
    ChatTurn,
    CapabilityHandler,
)
from .registry import Registry, discover_capabilities
from .router import Router
from .session import SessionStore, DEFAULT_DB_PATH

__all__ = [
    "Capability",
    "CapabilityResult",
    "CapabilityStatus",
    "CapabilityHandler",
    "ChatTurn",
    "Registry",
    "discover_capabilities",
    "Router",
    "SessionStore",
    "DEFAULT_DB_PATH",
    "ChatEngine",
]
