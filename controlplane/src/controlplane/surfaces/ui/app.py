"""Web UI surface for the AUTON chat control plane.

A tiny FastAPI app that serves one dependency-free chat page and proxies user
text to a :class:`ChatEngine` over the *shared* :class:`SessionStore`. Because it
reuses the same on-disk session (``~/.auton/session.db`` by default), the
conversation stays continuous with the terminal and desktop installs.

Endpoints
---------
``GET  /``            -> the chat page (static ``index.html``).
``POST /api/chat``    -> ``{text}`` -> ``engine.handle`` -> ``{text, handled, data}``.
``GET  /api/history`` -> the persisted session turns (oldest first).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from controlplane.core import ChatEngine, SessionStore

_STATIC_DIR = Path(__file__).parent / "static"

DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"


class ChatRequest(BaseModel):
    """Inbound chat utterance from the web client."""

    text: str = Field(min_length=1, description="The user's plain-English request.")


class ChatReply(BaseModel):
    """The result of routing one utterance, shaped for the web client."""

    text: str
    handled: bool
    data: dict


class HistoryTurn(BaseModel):
    """One persisted turn, serialized for the history view."""

    role: str
    text: str
    surface: str
    ts: float
    data: dict


def build_app(db_path: Path | str | None = None) -> FastAPI:
    """Construct the FastAPI app.

    ``db_path`` overrides the shared session location (used by tests for an
    isolated temp database); when omitted the default cross-surface store is used.
    """
    session = SessionStore(db_path) if db_path is not None else SessionStore()
    engine = ChatEngine(session=session, surface="ui")

    app = FastAPI(title="AUTON chat", docs_url=None, redoc_url=None)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    @app.post("/api/chat", response_model=ChatReply)
    def chat(req: ChatRequest) -> ChatReply:
        result = engine.handle(req.text)
        return ChatReply(text=result.text, handled=result.handled, data=result.data)

    @app.get("/api/history", response_model=list[HistoryTurn])
    def history() -> list[HistoryTurn]:
        return [
            HistoryTurn(
                role=turn.role,
                text=turn.text,
                surface=turn.surface,
                ts=turn.ts,
                data=turn.data,
            )
            for turn in session.history()
        ]

    # Serve app.js / style.css alongside the page.
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    return app


def main() -> None:
    """Console entrypoint (``auton-ui``): run uvicorn bound to localhost.

    Port resolution: ``--port N`` argument, else ``$AUTON_UI_PORT``, else 8765.
    """
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(prog="auton-ui", description="AUTON chat web UI")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("AUTON_UI_PORT", DEFAULT_PORT)),
        help=f"port to bind (default {DEFAULT_PORT} or $AUTON_UI_PORT)",
    )
    parser.add_argument(
        "--host", default=DEFAULT_HOST, help=f"host to bind (default {DEFAULT_HOST})"
    )
    args = parser.parse_args()

    uvicorn.run(build_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
