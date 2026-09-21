"""Pytest configuration and shared fixtures."""

import pytest

from orchestrator.llm import client as _llm_client


@pytest.fixture(autouse=True)
def _no_real_ollama(monkeypatch):
    """Keep the model preflight off whatever Ollama this host happens to run.

    Tests build engines with placeholder tags like ``ollama/test-model``. With
    no endpoint configured the preflight falls back to ``DEFAULT_OLLAMA_URL``,
    so a developer with Ollama running saw these fail and CI did not. Port 9
    (discard) refuses, which the preflight treats as "endpoint down" and skips.
    Tests of the preflight itself pass an explicit stub endpoint.
    """
    monkeypatch.setattr(_llm_client, "DEFAULT_OLLAMA_URL", "http://127.0.0.1:9")


@pytest.fixture
def sample_config():
    """Sample AUTON configuration."""
    return {
        "llm": {
            "model": "anthropic/claude-opus-4-6",
            "max_tokens": 16384,
            "temperature": 0.0,
        },
        "agents": {
            "developer_count": 4,
            "reviewer_count": 1,
        },
        "kernel": {
            "arch": "x86_64",
        },
        "validation": {
            "build_timeout": 120,
            "test_timeout": 60,
            "composition_checks": True,
        },
        "workflow": {
            "mode": "kernel_build",
        },
    }


@pytest.fixture
def sample_task():
    """Sample task definition."""
    return {
        "task_id": "boot-001",
        "title": "Implement boot loader",
        "subsystem": "boot",
        "description": "Create Multiboot2 boot loader",
        "dependencies": [],
        "acceptance_criteria": ["Kernel boots", "Serial output works"],
    }
