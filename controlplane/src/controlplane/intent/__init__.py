"""Free-form NL → capability intent resolution (LLM-first, rule fallback).

See :mod:`controlplane.intent.resolver`. Wire into the router with::

    from controlplane.core import Registry, Router
    from controlplane.intent import make_resolver

    router = Router(Registry(), intent_resolver=make_resolver(model="ollama/llama3.1:8b"))
"""

from __future__ import annotations

from .resolver import IntentResolver, make_resolver

__all__ = ["make_resolver", "IntentResolver"]
