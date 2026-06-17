"""Surface-agnostic chat engine.

Wires the registry, router, and session together and records every turn. The
terminal/UI/desktop surfaces each construct a :class:`ChatEngine` (sharing the
same :class:`SessionStore`) and feed it user text; they own their own I/O loop.

Mirrors ``kernels/x86_64/kernel/slm/chat.c`` (``slm_chat_loop``): a banner, the
``help``/``quit`` builtins, then dispatch — but here dispatch is the host router.
"""

from __future__ import annotations

from .contract import CapabilityResult, ChatTurn
from .registry import Registry
from .router import Router
from .session import SessionStore

BANNER = (
    "AUTON — chat control plane. Type a request in plain English "
    "(e.g. 'run nginx in docker', 'launch firefox', 'what's running').\n"
    "Type 'help' for capabilities, 'quit' to exit."
)

_QUIT_WORDS = ("quit", "exit", ":q")


def is_quit(text: str) -> bool:
    return text.strip().lower() in _QUIT_WORDS


def is_help(text: str) -> bool:
    return text.strip().lower() in ("help", "?", "what can you do", "capabilities")


class ChatEngine:
    def __init__(
        self,
        registry: Registry | None = None,
        router: Router | None = None,
        session: SessionStore | None = None,
        surface: str = "terminal",
    ) -> None:
        self.registry = registry or Registry()
        self.router = router or Router(self.registry)
        self.session = session or SessionStore()
        self.surface = surface

    def banner(self) -> str:
        return BANNER

    def help_text(self) -> str:
        """List capabilities with ready/roadmap status (deduped by name)."""
        lines = ["I can run these from chat:"]
        for cap in self.registry.unique_by_name():
            mark = "✓" if cap.status.value == "working" else "…"
            lines.append(f"  {mark} {cap.name} — {cap.note}")
        if len(lines) == 1:
            lines.append("  (no backends discovered yet)")
        return "\n".join(lines)

    def handle(self, text: str) -> CapabilityResult:
        """Record the user turn, route it, record AUTON's reply, return the result."""
        self.session.append(ChatTurn(role="user", text=text, surface=self.surface))

        if is_help(text):
            result = CapabilityResult.ok(self.help_text())
        else:
            result = self.router.route(text)

        self.session.append(
            ChatTurn(
                role="auton",
                text=result.text,
                surface=self.surface,
                data={"handled": result.handled, **result.data},
            )
        )
        return result
