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
    # The default stream is the path the graph's training task reads (w26 review:
    # it was vocab.json.tokens.jsonl, and slm-training looked for tokens.jsonl).
    from orchestrator.core.task_graph import TaskGraph
    training = next(t for t in TaskGraph().create_slm_training_tasks("g")
                    if t["task_id"] == "slm-training")
    assert "slm/work/tokens.jsonl" in training["description"]
    assert (Path(ws.path) / "slm/work/tokens.jsonl").exists()


async def test_a_corpus_that_does_not_fit_is_reported(ws):
    a = _agent(DataScientistAgent, ws)
    out = await a._execute_tool("check_vocab_budget", {"datasets": [
        "SLM/datasets/hardware_reference.jsonl"]})
    assert "DOES NOT FIT" in out and "[exit code: 1]" in out, out


def test_committed_configs_resolve_from_the_repository(ws):
    a = _agent(TrainingAgent, ws)
    assert a._slm_in("SLM/configs/chat_tiny.yaml").endswith("SLM/configs/chat_tiny.yaml")
    assert Path(a._slm_in("SLM/configs/chat_tiny.yaml")).exists()
    assert a._slm_out("slm/work/x.pt").startswith(str(ws.path))       # outputs stay put


def test_outputs_never_leave_the_workspace(ws):
    """The repository fallback is for reading committed inputs under SLM/ only
    (w26 review: build_corpus(output_dir="SLM/datasets") wrote over the tracked
    corpora, and absolute or `..` paths went anywhere)."""
    from orchestrator.comms.git_workspace import WorkspaceError
    a = _agent(TrainingAgent, ws)
    assert a._slm_out("SLM/datasets") == str(Path(ws.path) / "SLM" / "datasets")
    for bad in ("/root/.ssh/id_rsa", "/tmp/x", "../../../../etc/cron.d", "slm/../../x"):
        with pytest.raises(WorkspaceError):
            a._slm_out(bad)
        with pytest.raises(WorkspaceError):
            a._slm_in(bad)
    # Inputs: only committed files under SLM/ fall back to the repository.
    assert not a._slm_in("agent/config/auton.toml.example").startswith(str(a._slm_script("")))
    assert a._slm_in("agent/config/auton.toml.example").startswith(str(ws.path))


async def test_build_corpus_into_slm_datasets_writes_the_workspace_not_the_repo(ws):
    a = _agent(DataScientistAgent, ws)
    repo_copy = Path(a._slm_script("SLM/datasets/os_chat.jsonl"))
    before = repo_copy.stat().st_mtime_ns
    out = await a._execute_tool("build_corpus", {"output_dir": "SLM/datasets"})
    assert "[exit code: 0]" in out, out
    assert (Path(ws.path) / "SLM/datasets/os_chat.jsonl").exists()
    assert repo_copy.stat().st_mtime_ns == before


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


AUTON = (0x4E4F5455).to_bytes(4, "little") + b"\x03\x00\x00\x00rest"


async def test_integration_refuses_anything_but_the_auton_format(ws):
    a = _agent(IntegratorAgent, ws)
    (Path(ws.path) / "Makefile").write_text("iso-neural:\n")
    exp = Path(ws.path) / "slm" / "export"
    exp.mkdir(parents=True)
    for name, data in (("m.gguf", b"GGUF...."), ("m.GGUF", b"GGUF...."),
                       ("renamed.bin", b"GGUF...."), ("junk.bin", b"AUTN")):
        (exp / name).write_bytes(data)
        out = await a._execute_tool("integrate_slm", {"model_path": f"slm/export/{name}",
                                                      "kernel_arch": "x86_64"})
        assert out.startswith("Refused"), (name, out)
    assert not (Path(ws.path) / "models").exists()
    out = await a._execute_tool("integrate_slm", {"model_path": str(exp / "m.gguf"),
                                                  "kernel_arch": "x86_64"})
    assert "absolute" in out


async def test_integration_places_the_model_in_the_runs_kernel_tree(ws, tmp_path):
    """slm_training: the workspace holds no kernel; [slm] kernel_tree does (w26
    review: the model landed in the workspace, where nothing boots it)."""
    a = _agent(IntegratorAgent, ws)
    tree = tmp_path / "kernel"
    tree.mkdir()
    (tree / "Makefile").write_text("iso-neural:\n")
    a.kernel_tree = str(tree)
    (Path(ws.path) / "slm" / "export").mkdir(parents=True)
    (Path(ws.path) / "slm/export/auton-slm.bin").write_bytes(AUTON)
    out = await a._execute_tool("integrate_slm", {"model_path": "slm/export/auton-slm.bin",
                                                  "kernel_arch": "x86_64"})
    assert (tree / "models" / "auton-slm.bin").read_bytes() == AUTON, out
    assert not (Path(ws.path) / "models").exists()
    assert f"make -C {tree} iso-neural MODEL=models/auton-slm.bin" in out

    a.kernel_tree = None                     # no kernel tree, and no Makefile here
    out = await a._execute_tool("integrate_slm", {"model_path": "slm/export/auton-slm.bin",
                                                  "kernel_arch": "x86_64"})
    assert out.startswith("Refused") and "Makefile" in out


def test_every_slm_task_says_what_it_produces():
    from orchestrator.core.task_graph import TaskGraph
    tasks = TaskGraph().create_slm_training_tasks("ship a chat model")
    assert all(t["produces"] and t["acceptance_criteria"] for t in tasks)
    assert not any("gguf" in t["description"].lower() and "only if" not in t["description"]
                   for t in tasks)
