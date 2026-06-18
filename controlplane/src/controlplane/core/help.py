"""Capability help — the host answer to "what can you do".

Renders the registry's discovered capabilities the way the kernel's
``list_roles`` does: deduped by display name, each marked WORKING ("✓ ready")
or ROADMAP ("… roadmap"), one ``name — note`` line apiece. Pure and testable —
no I/O — so surfaces can print it and the UI can render the table form.
"""

from __future__ import annotations

from .contract import Capability, CapabilityStatus
from .registry import Registry

_HEADER = "Here's what I can do from chat:"
_FOOTER = "Say things like 'run nginx in docker' or 'launch firefox'."
_EMPTY = "  (no backends discovered yet)"

_MARKER_READY = "✓ ready"
_MARKER_ROADMAP = "… roadmap"


def _is_ready(cap: Capability) -> bool:
    return cap.status is CapabilityStatus.WORKING


def _marker(cap: Capability) -> str:
    return _MARKER_READY if _is_ready(cap) else _MARKER_ROADMAP


def _ordered(registry: Registry, ready_first: bool) -> list[Capability]:
    """Unique capabilities, optionally with WORKING ones surfaced first.

    Sorting is stable, so within each status group discovery order is kept.
    """
    caps = registry.unique_by_name()
    if not ready_first:
        return caps
    return sorted(caps, key=lambda c: 0 if _is_ready(c) else 1)


def format_capabilities(registry: Registry, *, ready_first: bool = True) -> str:
    """Human-readable capability listing for the chat help builtin.

    Deduped by display name; each line is ``<marker> <name> — <note>``. When
    ``ready_first`` is true, WORKING capabilities are listed before ROADMAP
    ones. An empty registry renders a graceful placeholder, never an error.
    """
    caps = _ordered(registry, ready_first)

    lines = [_HEADER]
    if caps:
        lines.extend(f"  {_marker(cap)}  {cap.name} — {cap.note}" for cap in caps)
    else:
        lines.append(_EMPTY)
    lines.append("")
    lines.append(_FOOTER)
    return "\n".join(lines)


def capabilities_table(registry: Registry) -> list[dict]:
    """Structured rows for a UI to render the same listing (deduped by name)."""
    return [
        {
            "name": cap.name,
            "status": cap.status.value,
            "ready": _is_ready(cap),
            "marker": _marker(cap),
            "note": cap.note,
        }
        for cap in registry.unique_by_name()
    ]
