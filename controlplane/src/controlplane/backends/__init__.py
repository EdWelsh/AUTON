"""Namespace package for control-plane backends.

Each backend is a subpackage ``controlplane.backends.<name>`` exposing a
``plugin.py`` with ``get_capabilities() -> list[Capability]``. The registry
discovers them at runtime (see ``controlplane.core.registry``), so adding a
backend never requires editing shared code.
"""
