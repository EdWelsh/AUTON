"""How the engine wires the specialist, SLM and vendor research swarms (w26 review).

Each test here failed before its fix:
- a subsystem whose tasks all went to its specialist was never designed;
- slm_training and research runs ended in an integrator model turn and a build
  of a workspace with no kernel, and reported failure whatever their tasks did;
- an SLM task was MERGED whenever its model replied, files or no files;
- the SLM swarm was told to read SLM/DATA.md and SLM/configs/, which its
  workspace-scoped tools cannot reach;
- a role with no agents was still advertised to the manager;
- two vendor tasks could share one branch;
- the Spec Reader's queue (exceptions.yaml) was out of its reach;
- a hardware record reached its reviewer without the mechanical check.

Only the model is scripted; the engine, workspace, graph and tools are real.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from orchestrator.core import engine as engine_module
from orchestrator.core import syntax_gate
from orchestrator.core.engine import OrchestrationEngine
from orchestrator.core.task_graph import TaskState

AGENT = Path(__file__).resolve().parents[3]
ROOT = AGENT.parent
sys.path.insert(0, str(AGENT / "tools"))

import vendor_research as vr  # noqa: E402

AUTON_BYTES = "UTON" + "\x03\x00\x00\x00" + "model"      # the AUTON magic, as text


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def _no_sleep(_):
        return None
    monkeypatch.setattr(engine_module.asyncio, "sleep", _no_sleep)


def _engine(tmp_path, **config):
    base = {"llm": {"model": "anthropic/scripted"},
            "orchestrator": {"max_iterations": 30, "max_review_rounds": 2},
            "agents": {"developer_count": 1, "reviewer_count": 1, "tester_count": 1},
            "validation": {"composition_checks": False}}
    for k, v in config.items():
        base[k] = {**base.get(k, {}), **v} if isinstance(v, dict) else v
    return OrchestrationEngine(workspace_path=tmp_path / "ws",
                               kernel_spec_path=AGENT / "kernel_spec", config=base)


def _say(text):
    return [{"role": "assistant", "content": text}]


# --- specialists are designed for ------------------------------------------- #

async def test_a_subsystem_given_to_a_specialist_is_designed(tmp_path, monkeypatch):
    eng = _engine(tmp_path, agents={"specialists": ["memory"]})
    eng.workspace.init()
    eng._init_agents()
    from orchestrator.core.state import OrchestratorState
    eng.state = OrchestratorState(run_id="t", goal="g", model="m")
    designed = []

    async def design(subsystem):
        designed.append(subsystem)
        return {}
    monkeypatch.setattr(eng._agents["architect"], "design_subsystem", design)
    await eng._design([
        {"task_id": "mm-001", "subsystem": "mm", "assigned_to": "memory_specialist"},
        {"task_id": "boot-001", "subsystem": "boot", "assigned_to": "developer"},
        {"task_id": "v-001", "subsystem": "hardware", "assigned_to": "vendor_scout"},
    ], tmp_path / "state.json")
    assert designed == ["boot", "mm"]


# --- the SLM swarm, end to end ---------------------------------------------- #

def _slm_engine(tmp_path):
    tree = tmp_path / "kernel"
    tree.mkdir()
    (tree / "Makefile").write_text("iso-neural:\n\t@true\n")
    eng = _engine(tmp_path, workflow={"mode": "slm_training"},
                  agents={"training_agent_count": 1}, slm={"kernel_tree": str(tree)})
    return eng, tree


class SLMModel:
    """Each SLM agent does what its task says, through its own tools."""

    def __init__(self, parity_exit=0):
        self.calls: list[tuple[str, str]] = []
        self.parity_exit = parity_exit
        self.read: dict[str, str] = {}

    async def __call__(self, agent_id, system, messages, tools, tool_executor, **_):
        prompt = messages[0]["content"]
        title = prompt.splitlines()[0]
        self.calls.append((agent_id, title))

        async def write(path, content="x\n"):
            await tool_executor("write_file", {"path": path, "content": content})
        if agent_id.startswith("data-scientist"):
            self.read["DATA.md"] = await tool_executor("read_file", {"path": "slm/DATA.md"})
            for p in ("slm/data/os_chat.jsonl", "slm/data/hardware_kernel.jsonl",
                      "slm/work/vocab.json", "slm/work/tokens.jsonl"):
                await write(p)
        elif agent_id.startswith("model-architect"):
            cfg = await tool_executor("read_file", {"path": "slm/configs/chat_tiny.yaml"})
            self.read["chat_tiny"] = cfg
            await write("slm/config.yaml", cfg)
            self.read["overwrite"] = await tool_executor(
                "write_file", {"path": "slm/configs/chat_tiny.yaml", "content": "x"})
        elif agent_id.startswith("training"):
            if "Train the model" in title:
                await write("slm/work/final.pt")
            elif "Evaluate" in title:
                await write("slm/work/auton-slm-fp32.bin")
                await tool_executor("run_parity", {"model_path": "m", "checkpoint_path": "c",
                                                   "vocab_path": "v"})
                await tool_executor("run_chat_eval", {"model_path": "m"})
                await write("slm/eval/fp32.json")
            elif "int8" in title:
                await write("slm/work/auton-slm-int8.bin")
                await tool_executor("run_parity", {"model_path": "m", "checkpoint_path": "c",
                                                   "vocab_path": "v"})
                await tool_executor("run_chat_eval", {"model_path": "m"})
                await write("slm/eval/int8.json")
            elif "Export" in title:
                await write("slm/export/auton-slm.bin", AUTON_BYTES)
        elif agent_id.startswith("integrator"):
            self.read["integrate"] = await tool_executor("integrate_slm", {
                "model_path": "slm/export/auton-slm.bin", "kernel_arch": "x86_64"})
        return _say("done")


def _stub_gates(monkeypatch, model):
    from orchestrator.agents.base_agent import Agent

    async def argv(self, cmd, timeout=120):
        rc = model.parity_exit if any("neural_parity" in c for c in cmd) else 0
        return f"ran\n[exit code: {rc}]"
    monkeypatch.setattr(Agent, "_run_argv", argv)


async def test_an_slm_run_ends_on_its_own_tasks_and_places_the_model_in_the_kernel_tree(
        tmp_path, monkeypatch):
    eng, tree = _slm_engine(tmp_path)
    model = SLMModel()
    _stub_gates(monkeypatch, model)
    monkeypatch.setattr(eng.client, "send_with_tools", model)

    result = await eng.run("ship a chat model")

    states = {n.task_id: n.state for n in eng.task_graph.all_tasks}
    assert set(states.values()) == {TaskState.MERGED}, states
    assert result["success"] is True, result
    assert "slm_training" in result["final_check"]["skipped"]
    assert result["build_ok"] is None
    # No model turn spent on a "Full integration check" of a kernel-less workspace.
    assert not any("Full integration check" in t for _, t in model.calls), model.calls
    # The seeded inputs were readable, and read-only.
    assert not model.read["DATA.md"].startswith("Error"), model.read["DATA.md"]
    assert model.read["DATA.md"] == (ROOT / "SLM" / "DATA.md").read_text()
    assert "vocab_size" in model.read["chat_tiny"]
    assert "read-only" in model.read["overwrite"]
    # The model is where the run's kernel boots it, with the command that does.
    assert (tree / "models" / "auton-slm.bin").read_text() == AUTON_BYTES
    assert not (eng.workspace.path / "models").exists()
    assert f"make -C {tree} iso-neural MODEL=models/auton-slm.bin" in model.read["integrate"]


async def test_an_slm_task_that_writes_nothing_is_not_done(tmp_path, monkeypatch):
    eng, _ = _slm_engine(tmp_path)

    async def idle(agent_id, system, messages, tools, tool_executor, **_):
        return _say("all done!")
    monkeypatch.setattr(eng.client, "send_with_tools", idle)

    result = await eng.run("ship a chat model")

    prep = eng.task_graph.get_task("slm-data-prep")
    assert prep.state is TaskState.FAILED
    assert "slm/work/tokens.jsonl" in prep.data["failure_reason"]
    assert eng.task_graph.get_task("slm-integration").state is not TaskState.MERGED
    assert result["success"] is False
    assert "slm-data-prep failed" in result["error"]


async def test_a_failed_parity_keeps_the_evaluation_open(tmp_path, monkeypatch):
    eng, tree = _slm_engine(tmp_path)
    model = SLMModel(parity_exit=1)
    _stub_gates(monkeypatch, model)
    monkeypatch.setattr(eng.client, "send_with_tools", model)

    result = await eng.run("ship a chat model")

    ev = eng.task_graph.get_task("slm-evaluation")
    assert ev.state is TaskState.FAILED
    assert "run_parity exited 1" in ev.data["failure_reason"]
    assert not (tree / "models").exists()
    assert result["success"] is False


async def test_slm_outputs_cannot_overwrite_the_repository(tmp_path):
    eng, _ = _slm_engine(tmp_path)
    eng.workspace.init()
    eng._seed_slm_inputs()
    eng._init_agents()
    ds = eng._agents["data_scientist"]
    out = await ds._execute_tool("tokenize_data", {"input_path": "slm/data",
                                                   "output_path": "slm/configs/chat_tiny.yaml"})
    assert "read-only" in out
    out = await ds._execute_tool("build_corpus", {"output_dir": str(ROOT / "SLM" / "datasets")})
    assert "absolute" in out


def test_the_slm_tasks_and_prompts_name_paths_the_swarm_can_read():
    """Every repository input the swarm is told to read is named at its seeded
    workspace copy; the repository's own paths are outside read_file's reach."""
    from orchestrator.arch_registry import get_arch_profile
    from orchestrator.core.engine import SLM_SEEDS
    from orchestrator.core.task_graph import TaskGraph
    from orchestrator.llm import prompts
    arch = get_arch_profile("x86_64")
    texts = [t["description"] + t["spec_reference"]
             for t in TaskGraph().create_slm_training_tasks("g")]
    texts += [prompts.build_data_scientist_prompt(arch),
              prompts.build_model_architect_prompt(arch)]
    joined = "\n".join(texts)
    assert "Read SLM/DATA.md" not in joined and "Start from SLM/configs" not in joined
    assert "slm/DATA.md" in joined and "slm/configs/chat_tiny.yaml" in joined
    assert set(SLM_SEEDS) == {"slm/DATA.md", "slm/configs"}
    assert all(src.exists() for src in SLM_SEEDS.values())


# --- vendor research --------------------------------------------------------- #

GOOD_PROPOSAL = """vendors:
  - vendor: zhaoxin
    category: cpu
    identity_keys: [family, model, stepping]
    documents: []
    gaps:
      - kind: errata
        reason: No public specification updates found.
"""


async def test_a_research_run_ends_on_its_own_tasks(tmp_path, monkeypatch):
    eng = _engine(tmp_path, agents={"developer_count": 0},
                  hardware={"research": True, "scout_count": 1, "reader_count": 0})
    calls = []

    async def model(agent_id, system, messages, tools, tool_executor, **_):
        prompt = messages[0]["content"]
        calls.append((agent_id, prompt.splitlines()[0]))
        if agent_id.startswith("manager") and "ecompose" in prompt:
            for tid in ("zhaoxin-001", "via-001"):
                await tool_executor("create_task", {
                    "task_id": tid, "title": f"Scout {tid}", "subsystem": "hardware",
                    "assigned_to": "vendor_scout", "description": "find documents",
                    "produces": ["hardware/proposals/zhaoxin.yaml"]})
            return _say("planned")
        if agent_id.startswith("vendor-scout"):
            await tool_executor("write_file", {"path": "hardware/proposals/zhaoxin.yaml",
                                               "content": GOOD_PROPOSAL}
                                if "zhaoxin" in prompt else
                                {"path": "hardware/proposals/via.yaml",
                                 "content": GOOD_PROPOSAL.replace("zhaoxin", "via-tech")})
            return _say("wrote it")
        return _say(json.dumps({"verdict": "approve", "summary": "ok", "issues": []}))
    monkeypatch.setattr(eng.client, "send_with_tools", model)

    result = await eng.run("scout two vendors")

    assert result["success"] is True, result
    assert "research" in result["final_check"]["skipped"]
    assert not any(a.startswith("integrator") for a, _ in calls), calls
    # One branch per task, not one per scout and task-id suffix.
    branches = {eng.task_graph.get_task(t).data["branch"] for t in ("zhaoxin-001", "via-001")}
    assert branches == {"agent/vendor-scout-01/hardware-zhaoxin-001",
                        "agent/vendor-scout-01/hardware-via-001"}


def test_a_role_with_no_agents_is_not_advertised(tmp_path):
    eng = _engine(tmp_path, hardware={"research": True, "scout_count": 0, "reader_count": 1})
    eng.workspace.init()
    eng._init_agents()
    roles = eng._agents["manager"].assignable_roles
    assert "vendor_scout" not in roles
    assert "spec_reader" in roles


def test_the_reader_and_its_manager_can_see_the_exceptions_queue(tmp_path):
    eng = _engine(tmp_path, hardware={"research": True, "scout_count": 0, "reader_count": 1})
    eng.workspace.init()
    eng._init_agents()
    reader = eng._agents["spec_reader-01"]
    rows = vr.unverified()
    assert rows and all(not r["cached"] or r["ref"] for r in rows)
    report = reader._hardware_tool("unverified_exceptions", {})
    assert f"{len(rows)} exceptions.yaml row(s) with verified: false" in report
    blocked = [r for r in rows if not r["cached"] and not r["fetchable"]]
    if blocked:
        assert "vendor_fetch.py" in report and "--from-file" in report
        assert "do not verify them from memory" in report
        note = next(n for n in eng._agents["manager"].role_notes if "spec_reader" in n)
        assert "--from-file" in note and blocked[0]["ref"] in note
    assert "unverified_exceptions" in {t["function"]["name"] for t in reader.tools}
    assert "unverified_exceptions" in reader.system_prompt


def test_the_queue_says_which_documents_an_operator_must_supply(tmp_path):
    table = tmp_path / "exceptions.yaml"
    table.write_text("exceptions:\n"
                     "  - {arch: x86, feature: fma4, vendor: intel, kind: never-shipped,\n"
                     "     applies_to: [], verified: false, verify_with: intel-sdm}\n"
                     "  - {arch: x86, feature: sse, vendor: intel, kind: removed,\n"
                     "     applies_to: [], verified: true, verify_with: intel-sdm}\n")
    rows = vr.unverified(table, cache=tmp_path / "cache")
    assert [(r["feature"], r["ref"], r["cached"]) for r in rows] == [
        ("fma4", "intel/intel-sdm", False)]
    report = vr.unverified_report(rows)
    assert "NOT CACHED" in report and "intel/intel-sdm" in report and "--from-file" in report


def test_a_hardware_record_is_checked_before_review(tmp_path):
    (tmp_path / "hardware" / "derived").mkdir(parents=True)
    (tmp_path / "hardware" / "proposals").mkdir()
    (tmp_path / "hardware/derived/bad.yaml").write_text(
        "format: 1\ndocument: {ref: nope/nope, sha256: x}\nrecords: []\n")
    (tmp_path / "hardware/proposals/intel.yaml").write_text(
        GOOD_PROPOSAL.replace("zhaoxin", "intel"))
    (tmp_path / "hardware/proposals/zhaoxin.yaml").write_text(GOOD_PROPOSAL)
    errors = syntax_gate.check(tmp_path, ["hardware/derived/bad.yaml",
                                          "hardware/proposals/intel.yaml"])
    assert errors and "hardware/derived/bad.yaml: no cached document" in errors
    assert "hardware/proposals/intel.yaml: vendor 'intel' is already in vendors.yaml" in errors
    assert syntax_gate.check(tmp_path, ["hardware/proposals/zhaoxin.yaml"]) is None
