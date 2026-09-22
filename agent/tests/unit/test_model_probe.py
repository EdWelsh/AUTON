"""The model qualification probe's verdicts (scripts/model-probe.py).

The probe decides whether a model may drive the loop, so its own judgement is
tested here with the model replaced by canned answers. The distinction that
matters: indentation a compiler ignores must pass, and characters corrupted
inside a token (the `ttypedef` that merged in w13) must fail.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("model_probe", ROOT / "scripts" / "model-probe.py")
probe = importlib.util.module_from_spec(spec)
sys.modules["model_probe"] = probe
spec.loader.exec_module(probe)


def answer(name="write_file", **args):
    call = SimpleNamespace(function=SimpleNamespace(name=name, arguments=json.dumps(args)))
    msg = SimpleNamespace(tool_calls=[call], content="")
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def prose(text="I will write the file."):
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(tool_calls=None, content=text))])


@pytest.fixture
def canned(monkeypatch):
    def install(response):
        monkeypatch.setattr(probe, "call", lambda *a, **k: response)
    return install


def test_prose_instead_of_a_tool_call_fails(canned):
    canned(prose())
    r = probe.check_tool_call("m")
    assert not r.ok and "no tool call" in r.detail


def test_a_tool_that_does_not_exist_fails(canned):
    """w13 F6: gemma4 called tftp_server_init, a C function from the spec."""
    canned(answer(name="tftp_server_init"))
    r = probe.check_tool_call("m")
    assert not r.ok and "tftp_server_init" in r.detail


def test_byte_exact_content_passes(canned):
    canned(answer(path="a.h", content=probe.FIDELITY_BODY))
    r = probe.check_fidelity("m")
    assert r.ok and "byte-exact" in r.detail


def test_different_indentation_passes_because_c_ignores_it(canned):
    canned(answer(path="a.h", content=probe.FIDELITY_BODY.replace("\t", "    ")))
    r = probe.check_fidelity("m")
    assert r.ok and "tokens identical" in r.detail


def test_a_corrupted_token_fails(canned):
    canned(answer(path="a.h", content=probe.FIDELITY_BODY.replace("\ttypedef", "ttypedef")))
    r = probe.check_fidelity("m")
    assert not r.ok and "corrupted" in r.detail


def test_the_long_prompt_check_wants_the_spec_s_own_signature(canned):
    canned(answer(path="kernel/include/mm.h", content="void pmm_init(const void *mmap);"))
    assert not probe.check_long_prompt("m").ok, "the spec says const boot_mmap_t *"
    canned(answer(path="kernel/include/mm.h", content="void pmm_init(const boot_mmap_t *mmap);"))
    assert probe.check_long_prompt("m").ok


def test_repeating_the_first_call_fails_the_second_turn(canned):
    canned(answer(path="kernel/include/a.h", content="#define A 1\n"))
    r = probe.check_second_turn("m")
    assert not r.ok and "repeated" in r.detail
    canned(answer(path="kernel/include/b.h", content="#define B 2\n"))
    assert probe.check_second_turn("m").ok


def test_a_provider_error_is_a_failure_not_a_crash(monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(probe, "call", boom)
    assert probe.probe("ollama_chat/nothing") is False
    assert "RuntimeError" in capsys.readouterr().out
