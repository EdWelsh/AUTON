"""Capability registry with runtime plugin discovery.

Backends live under ``controlplane.backends.<name>`` and expose a module
``plugin.py`` with a ``get_capabilities() -> list[Capability]`` function. The
registry discovers them at runtime, so adding a backend never requires editing
this file — each backend unit only adds files in its own subpackage.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil

from .contract import Capability

log = logging.getLogger(__name__)

BACKENDS_PACKAGE = "controlplane.backends"
PLUGIN_FACTORY = "get_capabilities"


def discover_capabilities(package: str = BACKENDS_PACKAGE) -> list[Capability]:
    """Import every ``<package>.<name>.plugin`` and collect its capabilities.

    Failures in one backend (missing optional dep, import error) are logged and
    skipped so a single broken plugin never takes down the whole chat.
    """
    capabilities: list[Capability] = []
    try:
        pkg = importlib.import_module(package)
    except ModuleNotFoundError:
        return capabilities

    for modinfo in pkgutil.iter_modules(pkg.__path__):
        if not modinfo.ispkg:
            continue
        plugin_name = f"{package}.{modinfo.name}.plugin"
        try:
            plugin = importlib.import_module(plugin_name)
        except ModuleNotFoundError:
            # Backend package without a plugin module — skip quietly.
            continue
        except Exception:  # noqa: BLE001 - a broken plugin must not break discovery
            log.exception("Failed to import backend plugin %s", plugin_name)
            continue

        factory = getattr(plugin, PLUGIN_FACTORY, None)
        if factory is None:
            continue
        try:
            capabilities.extend(factory())
        except Exception:  # noqa: BLE001
            log.exception("%s.%s() raised", plugin_name, PLUGIN_FACTORY)
    return capabilities


class Registry:
    """An ordered set of capabilities with first-match lookup.

    Order is preserved from discovery (and from ``register`` calls), so listing
    de-dupes by display name exactly like the kernel's ``list_roles``.
    """

    def __init__(self, capabilities: list[Capability] | None = None) -> None:
        self._caps: list[Capability] = (
            list(capabilities) if capabilities is not None else discover_capabilities()
        )

    @property
    def capabilities(self) -> list[Capability]:
        return list(self._caps)

    def register(self, capability: Capability) -> None:
        self._caps.append(capability)

    def match(self, text: str) -> Capability | None:
        """Return the first capability whose keywords appear in ``text``."""
        for cap in self._caps:
            if cap.matches(text):
                return cap
        return None

    def unique_by_name(self) -> list[Capability]:
        """Capabilities with duplicate display names collapsed to the first seen."""
        seen: set[str] = set()
        out: list[Capability] = []
        for cap in self._caps:
            if cap.name in seen:
                continue
            seen.add(cap.name)
            out.append(cap)
        return out
