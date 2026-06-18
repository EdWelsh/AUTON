"""Docker backend plugin — discovered at runtime by the registry."""

from __future__ import annotations

from controlplane.core import Capability, CapabilityStatus

from .client import handle


def get_capabilities() -> list[Capability]:
    """Expose the single WORKING docker capability."""
    return [
        Capability(
            name="docker",
            keywords=("docker", "container"),
            status=CapabilityStatus.WORKING,
            note="run/list/stop/logs/remove containers via the real docker CLI",
            handler=handle,
        )
    ]
