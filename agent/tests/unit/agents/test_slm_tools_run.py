"""The SLM swarm's tools run for real, from any workspace (w26).

Before w26 every SLM tool ran `python SLM/...` from inside the agent's workspace,
where no SLM/ exists, and integrate_slm copied a GGUF the kernel cannot load
into the repository's kernels/. The workflow tests only checked the task graph's
shape, so nothing noticed. These run the data half of the pipeline end to end
(no torch needed) and pin the integration rules.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.agents.data_scientist_agent import DataScientistAgent
from orchestrator.agents.integrator_agent import IntegratorAgent
from orchestrator.agents.training_agent import TrainingAgent
from orchestrator.comms.git_workspace import GitWorkspace


@pytest.fixture
def ws(tmp_path):
    w = GitWorkspace(tmp_path / "ws")
    w.init()
    return w


def _agent(cls, ws):
    return cls(agent_id="t-01", client=None, workspace=ws, message_bus=None,
               kernel_spec_path=Path(__file__).resolve().parents[3] / "kernel_spec")


async def test_the_data_scientist_builds_checks_and_tokenizes_a_kernel_set(ws):
    a = _agent(DataScientistAgent, ws)
    out = await a._execute_tool("build_corpus", {"output_dir": "slm/data"})
    assert "[exit code: 0]" in out, out
    data = Path(ws.path) / "slm" / "data"
    assert (data / "os_chat.jsonl").exists() and (data / "hardware_kernel.jsonl").exists()

    out = await a._execute_tool("check_vocab_budget", {"datasets": [
        "slm/data/os_chat.jsonl", "slm/data/hardware_kernel.jsonl"]})
    assert "FITS" in out and "[exit code: 0]" in out, out

    out = await a._execute_tool("tokenize_data", {"input_path": "slm/data",
                                                  "output_path": "slm/work/vocab.json"})
    assert "[exit code: 0]" in out, out
    vocab = json.loads((Path(ws.path) / "slm/work/vocab.json").read_text())
    assert len(vocab.get("vocab", vocab)) <= 1024
    assert (Path(ws.path) / "slm/work/vocab.json.tokens.jsonl").exists()


async def test_a_corpus_that_does_not_fit_is_reported(ws):
    a = _agent(DataScientistAgent, ws)
    out = await a._execute_tool("check_vocab_budget", {"datasets": [
        "SLM/datasets/hardware_reference.jsonl"]})
    assert "DOES NOT FIT" in out and "[exit code: 1]" in out, out


def test_committed_configs_resolve_from_the_repository(ws):
    a = _agent(TrainingAgent, ws)
    assert a._slm_path("SLM/configs/chat_tiny.yaml").endswith("SLM/configs/chat_tiny.yaml")
    assert Path(a._slm_path("SLM/configs/chat_tiny.yaml")).exists()
    assert a._slm_path("slm/work/x.pt").startswith(str(ws.path))       # outputs stay put


def test_validation_names_the_kernel_budgets(ws):
    a = _agent(TrainingAgent, ws)
    assert a._validate_architecture("SLM/configs/chat_tiny.yaml").startswith("Config valid")
    big = a._validate_architecture("SLM/configs/medium_150M.yaml")
    assert "vocab_size 32000 exceeds" in big


async def test_parity_and_eval_need_a_kernel_tree(ws):
    a = _agent(TrainingAgent, ws)
    a.kernel_tree = None
    for tool, args in (("run_parity", {"model_path": "m", "checkpoint_path": "c",
                                       "vocab_path": "v"}),
                       ("run_chat_eval", {"model_path": "m"})):
        assert (await a._execute_tool(tool, args)).startswith("Refused")


async def test_integration_refuses_gguf_and_stays_in_the_workspace(ws, tmp_path):
    a = _agent(IntegratorAgent, ws)
    g = tmp_path / "m.gguf"
    g.write_bytes(b"GGUF")
    assert (await a._execute_tool("integrate_slm", {"model_path": str(g),
                                                    "kernel_arch": "x86_64"})).startswith("Refused")
    b = tmp_path / "auton-slm.bin"
    b.write_bytes(b"AUTN")
    out = await a._execute_tool("integrate_slm", {"model_path": str(b), "kernel_arch": "x86_64"})
    assert (Path(ws.path) / "models" / "auton-slm.bin").read_bytes() == b"AUTN", out


def test_every_slm_task_says_what_it_produces():
    from orchestrator.core.task_graph import TaskGraph
    tasks = TaskGraph().create_slm_training_tasks("ship a chat model")
    assert all(t["produces"] and t["acceptance_criteria"] for t in tasks)
    assert not any("gguf" in t["description"].lower() and "only if" not in t["description"]
                   for t in tasks)
