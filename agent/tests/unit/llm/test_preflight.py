"""Model-availability preflight tests.

No mocks: a real HTTP server plays the Ollama ``/api/tags`` endpoint, so the
test exercises the same request path the preflight uses in production. The
point of the preflight is that a wrong model name fails at construction naming
the real alternatives, instead of surfacing as an empty completion several
tool-calls into an agent run.
"""

from __future__ import annotations

import http.server
import json
import threading

import pytest

from orchestrator.llm import client as client_module
from orchestrator.llm.client import (
    LLMClient,
    ModelUnavailableError,
    ProviderConfig,
    preflight_model,
)

INSTALLED = ["gemma4:latest", "qwen3.6:27B"]


def _make_tags_handler(models: list[str], status: int = 200):
    body = json.dumps({"models": [{"name": name} for name in models]}).encode()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's interface
            if self.path != "/api/tags":
                self.send_error(404)
                return
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep the test output clean
            pass

    return Handler


@pytest.fixture
def ollama_stub():
    """A real HTTP server answering /api/tags. Yields its base URL."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _make_tags_handler(INSTALLED))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


@pytest.fixture(autouse=True)
def clear_preflight_cache():
    """The per-process cache must not leak between tests."""
    client_module._preflight_ok.clear()
    yield
    client_module._preflight_ok.clear()


def _config(base_url: str) -> ProviderConfig:
    return ProviderConfig(endpoints={"ollama": base_url})


class TestPreflightModel:
    def test_missing_model_raises_naming_the_available_list(self, ollama_stub):
        with pytest.raises(ModelUnavailableError) as exc_info:
            preflight_model("ollama/not-a-real-model:v9", _config(ollama_stub))

        message = str(exc_info.value)
        assert "ollama/not-a-real-model:v9" in message, "names the model that was asked for"
        for installed in INSTALLED:
            assert installed in message, f"names the real option {installed}"
        assert "ollama pull not-a-real-model:v9" in message, "names the exact remedy"

    def test_installed_model_is_silent(self, ollama_stub):
        assert preflight_model("ollama/gemma4:latest", _config(ollama_stub)) is None

    def test_unreachable_endpoint_does_not_raise(self):
        # A down endpoint is a different failure with its own message; the
        # preflight must not turn "Ollama is starting" into "model missing".
        cfg = ProviderConfig(endpoints={"ollama": "http://127.0.0.1:1"})
        assert preflight_model("ollama/anything:latest", cfg) is None

    def test_empty_tag_list_reports_none_installed(self):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _make_tags_handler([]))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with pytest.raises(ModelUnavailableError, match="none installed"):
                preflight_model("ollama/gemma4:latest", _config(base))
        finally:
            server.shutdown()

    def test_cloud_provider_is_not_probed(self):
        # Cloud credentials are gated by cli.py's API-key check; duplicating it
        # here would recreate the two-sources-of-truth bug this phase removed.
        assert preflight_model("anthropic/claude-opus-4-6", ProviderConfig()) is None

    def test_ollama_chat_prefix_is_checked_too(self, ollama_stub):
        with pytest.raises(ModelUnavailableError):
            preflight_model("ollama_chat/nope:latest", _config(ollama_stub))

    def test_result_is_cached_per_process(self, ollama_stub):
        preflight_model("ollama/gemma4:latest", _config(ollama_stub))
        assert (ollama_stub, "gemma4:latest") in client_module._preflight_ok

        # With the endpoint gone, a cached pass must still be silent — the
        # preflight is one call per process, not one per turn.
        preflight_model("ollama/gemma4:latest", _config(ollama_stub))

    def test_default_endpoint_used_when_unconfigured(self, monkeypatch, ollama_stub):
        monkeypatch.setattr(client_module, "DEFAULT_OLLAMA_URL", ollama_stub)
        with pytest.raises(ModelUnavailableError):
            preflight_model("ollama/not-a-real-model:v9", ProviderConfig())


class TestLLMClientPreflight:
    def test_construction_fails_on_wrong_model(self, ollama_stub):
        with pytest.raises(ModelUnavailableError):
            LLMClient(model="ollama/not-a-real-model:v9", provider_config=_config(ollama_stub))

    def test_construction_succeeds_on_installed_model(self, ollama_stub):
        client = LLMClient(model="ollama/gemma4:latest", provider_config=_config(ollama_stub))
        assert client.model == "ollama/gemma4:latest"

    def test_preflight_can_be_disabled(self, ollama_stub):
        client = LLMClient(
            model="ollama/not-a-real-model:v9",
            provider_config=_config(ollama_stub),
            preflight=False,
        )
        assert client.model == "ollama/not-a-real-model:v9"


def test_ollama_chat_uses_the_ollama_endpoint():
    # `[llm.endpoints] ollama = ...` must reach ollama_chat/ models too, or they
    # silently probe and call the default host instead of the configured one.
    config = ProviderConfig(endpoints={"ollama": "http://gpu-box:11434"})
    assert config.get_base_url("ollama_chat/gemma4:latest") == "http://gpu-box:11434"
