"""Route an utterance to a capability.

Deterministic keyword matching first (cheap, offline, predictable). If nothing
matches and an optional intent resolver is wired in (Unit 8, backed by the agent
LLM client), fall back to it — mirroring the kernel's neural→rule-engine
fallback, but in reverse priority (rules first, model second).
"""

from __future__ import annotations

from typing import Callable, Optional

from .contract import CapabilityResult
from .registry import Registry

# An intent resolver maps free-form text + the registry to a capability (or None).
IntentResolver = Callable[[str, Registry], "Optional[object]"]


class Router:
    def __init__(
        self,
        registry: Registry,
        intent_resolver: IntentResolver | None = None,
    ) -> None:
        self.registry = registry
        self.intent_resolver = intent_resolver

    def route(self, text: str) -> CapabilityResult:
        cap = self.registry.match(text)
        if cap is None and self.intent_resolver is not None:
            cap = self.intent_resolver(text, self.registry)  # type: ignore[assignment]
        if cap is None:
            return CapabilityResult.unhandled(
                "I don't know how to do that yet. Try 'what can you do'."
            )
        return cap.handle(text)
