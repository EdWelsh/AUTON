"""The campaign runs on Sonnet (medium) and falls to the local model while the subscription is out."""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_runs_yaml_names_sonnet_with_a_local_fallback():
    spec = yaml.safe_load((ROOT / "docs/campaign/runs.yaml").read_text())
    assert spec["model"] == "claude-cli/claude-sonnet-5-5"
    assert spec["effort"] == "medium"
    assert spec["fallback_model"] == "ollama_chat/qwen3-coder:30b"


def test_generation_config_carries_the_fallback_model(tmp_path):
    gen = _load("generation_run_sw", "scripts/generation_run.py")
    cfg = gen.config(ROOT / "agent/config/auton.toml", tmp_path, "claude-cli/claude-sonnet-5-5",
                     tmp_path / "ws", 30, 1800, 32768, "ollama_chat/qwen3-coder:30b")
    llm = tomllib.loads(cfg.read_text())["llm"]
    assert llm["model"] == "claude-cli/claude-sonnet-5-5"
    assert llm["fallback_model"] == "ollama_chat/qwen3-coder:30b"
    assert llm["fallback_context"] == 32768
