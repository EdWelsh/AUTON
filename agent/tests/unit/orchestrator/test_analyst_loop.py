"""The Analyst in the real loop (A3 + A4).

Registration first, because it has a known silent failure: a role constructed
but not registered — or registered but not advertised — routes every task it is
given to nowhere (engine.py, w12). All three must hold.

Then the evidence gate, end to end: an Analyst that invents a capability is
refused *before any reviewer model sees the record*, is told the known names,
and its corrected record is the only one a reviewer is asked about.

Only the model is scripted.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from orchestrator.core import engine as engine_module
from orchestrator.core.engine import OrchestrationEngine
from orchestrator.core.task_graph import TaskState

AGENT = Path(__file__).resolve().parents[3]
SPECS = AGENT / "kernel_spec"
SUBJECT = AGENT / "tests" / "fixtures" / "apps" / "flask-hello"
VALID = AGENT / "tests" / "fixtures" / "artifacts" / "valid.artifact.yaml"
RECORD = "analysis/flask-hello.artifact.yaml"

TASKS = [{"task_id": "app-001", "title": "analyse flask-hello", "subsystem": "app",
          "assigned_to": "analyst", "dependencies": [], "produces": [RECORD],
          "description": "write the artifact record"}]


def _record(tree_hash: str, phantom: bool) -> str:
    data = yaml.safe_load(VALID.read_text())
    data["subject"]["tree_hash"] = tree_hash
    if phantom:
        data["facts"][0]["capability"] = "lib:libmagic-unicorn.so"
    return yaml.safe_dump(data, sort_keys=False)


class Model:
    def __init__(self):
        self.prompts: dict[str, list[str]] = {}
        self.reviewed: list[str] = []

    async def __call__(self, agent_id, system, messages, tools, tool_executor, **_):
        role = agent_id.split("-")[0]
        prompt = messages[0]["content"]
        self.prompts.setdefault(role, []).append(prompt)
        if role == "manager":
            if "## Goal" in prompt:
                return _say(json.dumps(TASKS))
            return _say(json.dumps({"progress_pct": 0}))
        if role == "analyst":
            tree_hash = re.search(r"tree_hash: ([0-9a-f]{64})", prompt).group(1)
            retry = "Review feedback" in prompt
            if retry:
                await tool_executor("read_file", {"path": RECORD})
            await tool_executor("write_file", {"path": RECORD,
                                               "content": _record(tree_hash, phantom=not retry)})
            return _say("wrote the record")
        if role == "reviewer":
            self.reviewed.append(prompt)
            return _say(json.dumps({"verdict": "approve", "summary": "ok", "issues": []}))
        return _say(json.dumps({"success": True}))


def _say(text):
    return [{"role": "assistant", "content": text}]


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "README.md").write_text("base\n")
    subprocess.run(["git", "init", "-q", "-b", "main", str(ws)], check=True)
    subprocess.run(["git", "-C", str(ws), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(ws), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], check=True)
    return ws


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    real = asyncio.sleep

    async def fast(_):
        await real(0)
    monkeypatch.setattr(engine_module.asyncio, "sleep", fast)


def _engine(ws, subject=SUBJECT):
    return OrchestrationEngine(
        workspace_path=ws, kernel_spec_path=SPECS, subject_path=subject,
        config={"llm": {"model": "anthropic/scripted"},
                "orchestrator": {"max_iterations": 10, "max_review_rounds": 3},
                "agents": {"developer_count": 1, "reviewer_count": 1, "tester_count": 1},
                "validation": {"composition_checks": False}})


# --------------------------------------------------------------------------- #
# Registration: constructed, registered, advertised — all three
# --------------------------------------------------------------------------- #

async def test_the_analyst_is_constructed_registered_and_advertised(workspace, monkeypatch):
    eng = _engine(workspace)
    model = Model()
    monkeypatch.setattr(eng.client, "send_with_tools", model)
    await eng.run("analyse the staged application")

    assert "analyst" in eng._agents, "constructed"
    assert eng.scheduler.status()["analyst"]["total"] == 1, "registered"
    decomposition = model.prompts["manager"][0]
    assert '"analyst"' in decomposition and ".auton/subject/" in decomposition, "advertised"
    node = eng.task_graph.get_task("app-001")
    assert node.assigned_agent_id == "analyst-01", "and a task for it was dispatched"


async def test_with_no_subject_the_analyst_is_not_advertised(workspace, monkeypatch):
    eng = _engine(workspace, subject=None)
    model = Model()
    monkeypatch.setattr(eng.client, "send_with_tools", model)
    await eng.run("build something")
    assert "analyst" not in eng._agents
    assert '"analyst"' not in model.prompts["manager"][0], \
        "a role advertised but not registered is the w12 empty-pool failure"


# --------------------------------------------------------------------------- #
# The evidence gate, in the loop
# --------------------------------------------------------------------------- #

async def test_an_invented_capability_never_reaches_a_reviewer(workspace, monkeypatch):
    eng = _engine(workspace)
    model = Model()
    monkeypatch.setattr(eng.client, "send_with_tools", model)
    await eng.run("analyse the staged application")

    node = eng.task_graph.get_task("app-001")
    assert node.state is TaskState.MERGED, node.data.get("failure_reason")
    assert node.review_rounds == 1, "refused once, by the tool"
    refusal = node.data["review_feedback"][0]["summary"]
    assert "libmagic-unicorn" in refusal and "Known lib names" in refusal
    assert "libssl.so.3" in refusal, "the refusal lists what is known"
    assert len(model.reviewed) == 1, "the reviewer model saw only the corrected record"
    assert "libmagic-unicorn" not in (workspace / RECORD).read_text()


async def test_the_analyst_sees_the_subject_and_the_index(workspace, monkeypatch):
    eng = _engine(workspace)
    model = Model()
    monkeypatch.setattr(eng.client, "send_with_tools", model)
    await eng.run("analyse the staged application")
    first = model.prompts["analyst"][0]
    assert eng.subject_hash in first
    assert "- lib: " in first and "libssl.so.3" in first
    assert "syscalls" not in first, "a disabled kind is not offered"


async def test_a_subject_changed_mid_run_refuses_the_record(workspace, monkeypatch):
    eng = _engine(workspace)
    model = Model()
    original = model.__call__

    async def tamper(agent_id, system, messages, tools, tool_executor, **kw):
        if agent_id.startswith("analyst"):
            target = workspace / ".auton" / "subject" / "app.py"
            target.chmod(0o644)
            target.write_text("# edited by the analysis\n")
        return await original(agent_id, system, messages, tools, tool_executor, **kw)
    monkeypatch.setattr(eng.client, "send_with_tools", tamper)
    await eng.run("analyse the staged application")

    node = eng.task_graph.get_task("app-001")
    assert node.state is TaskState.FAILED
    assert "subject changed" in node.data["failure_reason"]
    assert model.reviewed == []


async def test_analysis_tasks_do_not_trigger_kernel_design(workspace, monkeypatch):
    """w18 live run 2: the manager labelled analyst tasks `sys`/`pkg` and the
    architect then designed kernel headers for them."""
    eng = _engine(workspace)
    model = Model()
    monkeypatch.setattr(eng.client, "send_with_tools", model)
    await eng.run("analyse the staged application")
    assert "architect" not in model.prompts, "no kernel task, so nothing to design"


async def test_the_analyst_can_check_its_record_before_the_gate(workspace, monkeypatch):
    from orchestrator.agents.analyst_agent import AnalystAgent  # noqa: F401
    eng = _engine(workspace)
    monkeypatch.setattr(eng.client, "send_with_tools", Model())
    await eng.run("analyse the staged application")
    analyst = eng._agents["analyst"]
    (workspace / "analysis").mkdir(exist_ok=True)
    (workspace / "analysis" / "bad.artifact.yaml").write_text("facts: [unclosed\n")
    out = await analyst._execute_tool("check_record", {"path": "analysis/bad.artifact.yaml"})
    assert out.startswith("NOT OK") and "YAML" in out
    out = await analyst._execute_tool("check_record", {"path": RECORD})
    assert out.startswith("OK")
