"""A run cut off by its time budget keeps its work and resumes.

R1 (w15, qwen3.5:27b) ran for exactly ORCH_TIMEOUT=18000 and was killed: one of
six tasks approved, and a 13,982-byte `pmm.c` on disk that was never committed.
`OrchestratorState` said "crash recovery" and saved no task graph, and
`engine.run()` always re-planned, so the next run would have started from
nothing — possibly with a different decomposition.

Only the model is scripted; engine, scheduler, graph, workspace and git are real.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.core import engine as engine_module
from orchestrator.core.engine import OrchestrationEngine
from orchestrator.core.state import OrchestratorState
from orchestrator.core.task_graph import TaskGraph, TaskState

SPECS = Path(__file__).resolve().parents[3] / "kernel_spec"
GOAL = "write a then b"
TASKS = [
    {"task_id": "k-001", "title": "add a", "subsystem": "lib", "assigned_to": "developer",
     "dependencies": [], "produces": ["kernel/lib/a.c"], "description": "write a"},
    {"task_id": "k-002", "title": "add b", "subsystem": "lib", "assigned_to": "developer",
     "dependencies": ["k-001"], "produces": ["kernel/lib/b.c"], "description": "write b"},
]


class Model:
    """Scripted by role. With `pause_on` set, the developer writing that file
    requests a pause mid-task (as SIGTERM would) and then hangs, like a model
    call still in flight when the budget runs out."""

    def __init__(self, engine=None, pause_on: str | None = None, real_signal=False):
        self.engine = engine
        self.pause_on = pause_on
        self.real_signal = real_signal
        self.calls: dict[str, int] = {}
        self.prompts: list[str] = []

    async def __call__(self, agent_id, system, messages, tools, tool_executor, **_):
        role = agent_id.split("-")[0]
        self.calls[role] = self.calls.get(role, 0) + 1
        prompt = messages[0]["content"]
        self.prompts.append(prompt)
        if role == "manager":
            if "ecompose" in prompt:
                return _say(json.dumps(TASKS))
            return _say(json.dumps({"progress_pct": 0}))
        if role == "dev":
            name = "a" if "add a" in prompt else "b"
            path = f"kernel/lib/{name}.c"
            if self.pause_on == path:
                await tool_executor("write_file", {"path": path, "content": "int a = 1; /* half */\n"})
                if self.real_signal:
                    os.kill(os.getpid(), signal.SIGTERM)
                else:
                    self.engine.request_pause()
                await asyncio.Event().wait()   # never returns; cancelled by the pause
            if "resumed" in prompt.lower():
                await tool_executor("read_file", {"path": path})
            await tool_executor("write_file", {"path": path, "content": f"int {name} = 1;\n"})
            return _say(f"wrote {path}")
        if role == "reviewer":
            return _say(json.dumps({"verdict": "approve", "summary": "ok", "issues": []}))
        return _say(json.dumps({"success": True}))


def _say(text):
    return [{"role": "assistant", "content": text}]


def _git(ws, *args):
    return subprocess.run(["git", "-C", str(ws), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "README.md").write_text("base\n")
    subprocess.run(["git", "init", "-q", "-b", "main", str(ws)], check=True)
    _git(ws, "add", "-A")
    subprocess.run(["git", "-C", str(ws), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], check=True)
    return ws


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    real_sleep = asyncio.sleep

    async def fast(_):
        await real_sleep(0)
    monkeypatch.setattr(engine_module.asyncio, "sleep", fast)


def _engine(ws, model_name="anthropic/scripted"):
    return OrchestrationEngine(
        workspace_path=ws, kernel_spec_path=SPECS,
        config={"llm": {"model": model_name},
                "orchestrator": {"max_iterations": 10, "max_review_rounds": 3},
                "agents": {"developer_count": 1, "reviewer_count": 1, "tester_count": 1},
                "validation": {"composition_checks": False}})


async def _paused_run(ws, monkeypatch, real_signal=False):
    eng = _engine(ws)
    model = Model(pause_on="kernel/lib/a.c", real_signal=real_signal)
    model.engine = eng
    monkeypatch.setattr(eng.client, "send_with_tools", model)
    return eng, await eng.run(GOAL)


# --------------------------------------------------------------------------- #
# The graph persists
# --------------------------------------------------------------------------- #

def test_the_graph_round_trips():
    g = TaskGraph()
    g.add_tasks([dict(t) for t in TASKS])
    g.assign_agent("k-001", "dev-01")
    g.requeue("k-001", {"verdict": "request_changes", "summary": "again"})
    restored = TaskGraph.from_dict(json.loads(json.dumps(g.to_dict())))
    a, b = restored.get_task("k-001"), restored.get_task("k-002")
    assert a.state is TaskState.READY and a.review_rounds == 1
    assert a.data["review_feedback"][0]["summary"] == "again"
    assert a.assigned_agent_id == "dev-01"
    assert b.state is TaskState.PENDING and b.dependencies == ["k-001"]
    restored.update_state("k-001", TaskState.MERGED)
    assert b.state is TaskState.READY, "reverse dependencies are rebuilt too"


def test_a_state_file_from_before_resume_says_so(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"run_id": "r", "goal": "g", "phase": "developing"}))
    assert OrchestratorState.load(path).format == 1


# --------------------------------------------------------------------------- #
# A pause keeps the work
# --------------------------------------------------------------------------- #

async def test_a_pause_commits_the_work_in_flight(workspace, monkeypatch):
    eng, result = await _paused_run(workspace, monkeypatch)

    assert result.get("paused") is True, result
    node = eng.task_graph.get_task("k-001")
    branch = node.data["resume_branch"]
    assert "a = 1; /* half */" in _git(workspace, "show", f"{branch}:kernel/lib/a.c"), \
        "the half-written file is committed on its own branch, not lost"
    assert _git(workspace, "rev-parse", "--abbrev-ref", "HEAD") == "main"

    state = OrchestratorState.load(workspace / ".auton" / "state.json")
    assert state.phase == "paused"
    assert {n["task_id"] for n in state.graph} == {"k-001", "k-002"}


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM delivery is POSIX-only")
async def test_a_real_sigterm_pauses_rather_than_kills(workspace, monkeypatch):
    _, result = await _paused_run(workspace, monkeypatch, real_signal=True)
    assert result.get("paused") is True, result
    assert signal.getsignal(signal.SIGTERM) in (signal.SIG_DFL, signal.default_int_handler), \
        "the handler is removed when the run ends"


# --------------------------------------------------------------------------- #
# Resume continues without re-planning
# --------------------------------------------------------------------------- #

async def test_resume_skips_planning_and_design_and_finishes(workspace, monkeypatch):
    await _paused_run(workspace, monkeypatch)

    eng = _engine(workspace)
    model = Model()
    monkeypatch.setattr(eng.client, "send_with_tools", model)
    result = await eng.run(GOAL, resume=True)

    assert not result.get("resume_refused"), result
    manager_decomposed = [p for p in model.prompts if "## Goal" in p]
    assert manager_decomposed == [], "a resumed run does not decompose again"
    assert model.calls.get("architect", 0) == 0, "nor does it redesign"
    nodes = {n.task_id: n for n in eng.task_graph.all_tasks}
    assert nodes["k-001"].state is TaskState.MERGED
    assert nodes["k-002"].state is TaskState.MERGED
    assert any("resumed" in p.lower() for p in model.prompts), \
        "the agent is told its branch already holds its earlier work"
    assert (workspace / "kernel/lib/a.c").read_text() == "int a = 1;\n"
    assert OrchestratorState.load(workspace / ".auton" / "state.json").resume_count == 1


async def test_resume_refuses_a_different_goal(workspace, monkeypatch):
    await _paused_run(workspace, monkeypatch)
    result = await _engine(workspace).run("something else", resume=True)
    assert "goal" in result["resume_refused"]


async def test_resume_refuses_when_main_moved(workspace, monkeypatch):
    await _paused_run(workspace, monkeypatch)
    (workspace / "other.txt").write_text("x\n")
    _git(workspace, "add", "other.txt")
    subprocess.run(["git", "-C", str(workspace), "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "-qm", "moved"], check=True)
    result = await _engine(workspace).run(GOAL, resume=True)
    assert "main" in result["resume_refused"]


async def test_resume_refuses_a_model_change(workspace, monkeypatch):
    await _paused_run(workspace, monkeypatch)
    result = await _engine(workspace, "anthropic/other").run(GOAL, resume=True)
    assert "model" in result["resume_refused"]


async def test_resume_refuses_an_old_state_file(workspace):
    auton = workspace / ".auton"
    auton.mkdir()
    (auton / "state.json").write_text(json.dumps({"run_id": "r", "goal": GOAL}))
    result = await _engine(workspace).run(GOAL, resume=True)
    assert "format" in result["resume_refused"]


async def test_resume_refuses_with_nothing_to_resume(workspace):
    result = await _engine(workspace).run(GOAL, resume=True)
    assert "no saved run" in result["resume_refused"]


async def test_a_fresh_run_does_not_inherit_a_paused_state(workspace, monkeypatch):
    await _paused_run(workspace, monkeypatch)
    eng = _engine(workspace)
    model = Model()
    monkeypatch.setattr(eng.client, "send_with_tools", model)
    await eng.run(GOAL)
    assert any("## Goal" in p for p in model.prompts), "a new run plans from scratch"
    assert OrchestratorState.load(workspace / ".auton" / "state.json").resume_count == 0


async def test_a_second_session_killed_outright_can_still_resume(workspace, monkeypatch):
    """w17 review: head_at_save survived a resume, so a session that moved main
    and was then killed (not paused) could never be resumed again."""
    await _paused_run(workspace, monkeypatch)
    state_path = workspace / ".auton" / "state.json"

    eng = _engine(workspace)
    model = Model()
    monkeypatch.setattr(eng.client, "send_with_tools", model)
    await eng.run(GOAL, resume=True)          # merges: main moves
    state = OrchestratorState.load(state_path)
    state.phase = "developing"                # as a SIGKILL would leave it
    state.save(state_path)

    result = await _engine(workspace).run(GOAL, resume=True)
    assert not result.get("resume_refused"), result


async def test_a_pause_that_cannot_commit_still_saves_and_says_so(workspace, monkeypatch):
    eng = _engine(workspace)
    model = Model(pause_on="kernel/lib/a.c")
    model.engine = eng
    monkeypatch.setattr(eng.client, "send_with_tools", model)

    real = eng.workspace.commit_pending

    def locked(*a, **k):
        if eng._pause_requested:
            raise RuntimeError("index.lock exists")
        return real(*a, **k)
    monkeypatch.setattr(eng.workspace, "commit_pending", locked)
    result = await eng.run(GOAL)

    assert result.get("paused") is True
    assert "index.lock" in result["pause_warning"]
    assert OrchestratorState.load(workspace / ".auton" / "state.json").phase == "paused"


async def test_a_resume_skips_subsystems_already_designed(workspace, monkeypatch):
    """w18 R1: design was recorded only as a whole phase, so a pause inside it
    restarted every subsystem's design on resume, four sessions running."""
    tasks = [dict(t) for t in TASKS] + [
        {"task_id": "k-003", "title": "add c", "subsystem": "mm", "assigned_to": "developer",
         "dependencies": [], "produces": ["kernel/mm/c.c"], "description": "write c"}]
    eng = _engine(workspace)
    designed = []

    async def model(agent_id, system, messages, tools, tool_executor, **_):
        prompt = messages[0]["content"]
        if agent_id.startswith("manager"):
            return _say(json.dumps(tasks) if "ecompose" in prompt else "{}")
        if agent_id.startswith("architect"):
            designed.append(prompt)
            if len(designed) == 2:          # pause inside the second subsystem's design
                eng.request_pause()
                await asyncio.Event().wait()
            return _say("designed")
        return _say(json.dumps({"verdict": "approve", "summary": "ok", "issues": []}))
    monkeypatch.setattr(eng.client, "send_with_tools", model)
    result = await eng.run(GOAL)
    assert result.get("paused")
    first = OrchestratorState.load(workspace / ".auton" / "state.json").designed
    assert len(first) == 1, first

    eng2 = _engine(workspace)
    again = []

    async def model2(agent_id, system, messages, tools, tool_executor, **_):
        if agent_id.startswith("architect"):
            again.append(messages[0]["content"])
        return await Model()(agent_id, system, messages, tools, tool_executor)
    monkeypatch.setattr(eng2.client, "send_with_tools", model2)
    await eng2.run(GOAL, resume=True)
    assert len(again) == 1, "only the subsystem not yet designed is designed again"
    assert first[0] not in again[0]
