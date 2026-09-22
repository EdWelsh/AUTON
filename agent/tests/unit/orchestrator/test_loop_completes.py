"""A goal's task chain completes: the test w11 lacked.

Only the model is scripted. The engine, scheduler, task graph, workspace,
agents, review routing and merge are the real ones. Before w12 this chain could
not finish: a read task went to review as `main`, a rejection was terminal, and
an approval never reached MERGED.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from orchestrator.core import engine as engine_module
from orchestrator.core.engine import OrchestrationEngine
from orchestrator.core.task_graph import TaskState

TASKS = [
    {"task_id": "k-001", "title": "add a", "subsystem": "lib", "assigned_to": "developer",
     "dependencies": [], "produces": ["kernel/lib/a.c"], "description": "write a"},
    {"task_id": "k-002", "title": "add b", "subsystem": "lib", "assigned_to": "developer",
     "dependencies": ["k-001"], "produces": ["kernel/lib/b.c"], "description": "write b"},
    {"task_id": "k-000", "title": "Read Architecture Specification", "subsystem": "architecture",
     "assigned_to": "architect", "dependencies": [], "description": "read it"},
]


class ScriptedModel:
    """Answers by role. The first review of k-001 asks for changes."""

    def __init__(self):
        self.reviews: dict[str, int] = {}

    async def __call__(self, agent_id, system, messages, tools, tool_executor, **_):
        prompt = messages[0]["content"]
        if agent_id.startswith("manager"):
            if "Decompose" in prompt or "decompose" in prompt:
                return self._say(json.dumps(TASKS))
            return self._say(json.dumps({"progress_pct": 0}))
        if agent_id.startswith("dev"):
            task_id = "k-001" if "add a" in prompt else "k-002"
            name = "a" if task_id == "k-001" else "b"
            revised = "Review feedback" in prompt
            body = f"int {name} = {2 if revised else 1};\n"
            path = f"kernel/lib/{name}.c"
            if revised:
                await tool_executor("read_file", {"path": path})
            await tool_executor("write_file", {"path": path, "content": body})
            return self._say(f"wrote {path}")
        if agent_id.startswith("reviewer"):
            task_id = "k-001" if "k-001" in prompt else "k-002"
            self.reviews[task_id] = self.reviews.get(task_id, 0) + 1
            if task_id == "k-001" and self.reviews[task_id] == 1:
                return self._say(json.dumps({
                    "verdict": "request_changes", "summary": "a should be 2",
                    "issues": [{"severity": "warning", "file": "kernel/lib/a.c",
                                "line": 1, "description": "a should be 2"}]}))
            return self._say(json.dumps({"verdict": "approve", "summary": "ok", "issues": []}))
        return self._say(json.dumps({"success": True}))

    @staticmethod
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


async def test_a_two_task_chain_completes_through_one_rejection(workspace, monkeypatch):
    async def no_sleep(_):
        return None
    monkeypatch.setattr(engine_module.asyncio, "sleep", no_sleep)

    specs = Path(__file__).resolve().parents[3] / "kernel_spec"
    eng = OrchestrationEngine(
        workspace_path=workspace, kernel_spec_path=specs,
        config={"llm": {"model": "anthropic/scripted"},
                "orchestrator": {"max_iterations": 10, "max_review_rounds": 3},
                "agents": {"developer_count": 1, "reviewer_count": 1, "tester_count": 1},
                "validation": {"composition_checks": False}})
    model = ScriptedModel()
    monkeypatch.setattr(eng.client, "send_with_tools", model)

    result = await eng.run("write a then b")

    nodes = {n.task_id: n for n in eng.task_graph.all_tasks}
    assert set(nodes) == {"k-001", "k-002"}, "the read-only task is dropped at planning"
    assert nodes["k-001"].state is TaskState.MERGED
    assert nodes["k-002"].state is TaskState.MERGED
    assert nodes["k-001"].review_rounds == 1
    assert (workspace / "kernel/lib/a.c").read_text() == "int a = 2;\n", "the revision merged"
    assert (workspace / "kernel/lib/b.c").exists()
    # No Makefile, so the final build fails, and the run must say so rather
    # than `failed: unknown`.
    assert result["success"] is False
    assert "build failed" in result["error"]
