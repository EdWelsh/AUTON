"""E2E tests for the web UI surface — real app, real ChatEngine, no mocks.

The app is exercised through FastAPI's ``TestClient`` over a temp SessionStore so
the persisted conversation stays continuous with the terminal/desktop installs.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from controlplane.surfaces.ui.app import build_app


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    app = build_app(db_path=tmp_path / "session.db")
    return TestClient(app)


def test_index_serves_chat_page(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text.lower()
    assert "auton" in body
    # Intentional chat page, not an empty shell.
    assert "<form" in body or 'id="chat' in body


def test_chat_returns_result_shape_and_persists(client: TestClient) -> None:
    resp = client.post("/api/chat", json={"text": "what can you do"})
    assert resp.status_code == 200

    payload = resp.json()
    assert set(payload) >= {"text", "handled", "data"}
    assert isinstance(payload["text"], str) and payload["text"]
    assert isinstance(payload["handled"], bool)
    assert isinstance(payload["data"], dict)

    # The turn must be reflected in the shared session history.
    hist = client.get("/api/history").json()
    assert isinstance(hist, list)
    roles = [turn["role"] for turn in hist]
    texts = [turn["text"] for turn in hist]
    assert "user" in roles and "auton" in roles
    assert "what can you do" in texts
    # The UI surface must tag its turns so the conversation is attributable.
    assert any(turn["surface"] == "ui" for turn in hist)


def test_chat_rejects_missing_text(client: TestClient) -> None:
    resp = client.post("/api/chat", json={})
    assert resp.status_code == 422


def test_history_starts_empty(client: TestClient) -> None:
    assert client.get("/api/history").json() == []
