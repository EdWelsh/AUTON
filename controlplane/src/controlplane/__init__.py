"""AUTON host chat control plane.

A natural-language chat that routes utterances to *capabilities* which run real
workloads on the host (desktop apps, Docker, Kubernetes, server processes). The
design mirrors the in-kernel role registry in ``kernels/x86_64/kernel/slm/roles.c``:
each capability has trigger keywords, a display name, a status, and an action.

Public contract (stable; backends and surfaces build against this):
    from controlplane.core import (
        Capability, CapabilityResult, CapabilityStatus, ChatTurn,
        Registry, Router, SessionStore, ChatEngine,
    )
"""

from __future__ import annotations

__version__ = "0.1.0"
