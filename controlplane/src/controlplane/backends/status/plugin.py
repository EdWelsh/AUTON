"""Status backend plugin — exposes the "what's running" capability."""

from __future__ import annotations

from controlplane.core import Capability, CapabilityResult, CapabilityStatus

from .aggregator import collect_snapshot


def _handle(text: str) -> CapabilityResult:
    snapshot = collect_snapshot()
    rendered = snapshot.render()
    available = [r.name for r in snapshot.reports if r.available]
    return CapabilityResult.ok(rendered or "Nothing is running.", sources=available)


def get_capabilities() -> list[Capability]:
    return [
        Capability(
            name="status",
            keywords=("what's running", "whats running", "status", "overview"),
            status=CapabilityStatus.WORKING,
            note="live snapshot across Docker, Kubernetes, and host server processes",
            handler=_handle,
        ),
    ]
