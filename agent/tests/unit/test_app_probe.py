"""The external probe's verdict logic (A10), without Docker."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from app_probe import ProbeError, judge, load_probe  # noqa: E402

HTTP = {"kind": "http", "port": 8000, "path": "/health", "expect_status": 200,
        "expect_body_contains": "ok"}


def test_a_matching_answer_passes():
    assert judge(HTTP, {"status": 200, "body": "ok"}) is None


def test_a_wrong_status_names_both():
    why = judge(HTTP, {"status": 500, "body": ""})
    assert "500" in why and "200" in why


def test_a_missing_body_is_quoted():
    assert "lacks 'ok'" in judge(HTTP, {"status": 200, "body": "nope"})


def test_a_connection_error_fails_the_check():
    assert "ConnectionRefused" in judge(HTTP, {"error": "ConnectionRefusedError: x"})


def test_exec_and_tcp():
    assert judge({"kind": "exec", "command": ["true"]}, {"exit": 0}) is None
    assert "exited 3" in judge({"kind": "exec", "command": ["x"]}, {"exit": 3})
    assert judge({"kind": "tcp", "port": 6379, "expect": "PONG"}, {"body": "+PONG"}) is None
    assert judge({"kind": "tcp", "port": 6379, "expect": "PONG"}, {"body": ""})


def test_no_declaration_means_the_probe_cannot_run(tmp_path):
    with pytest.raises(ProbeError, match="declared by a person"):
        load_probe(tmp_path / "probe.yaml")


def test_an_unknown_check_kind_is_refused(tmp_path):
    p = tmp_path / "probe.yaml"
    p.write_text("checks: [{kind: vibes}]\n")
    with pytest.raises(ProbeError, match="vibes"):
        load_probe(p)
