"""The Packager in the real loop, gated by a real build (A8).

Registration: constructed, registered and advertised only when a manifest's
substrate is a container. Then the gate end to end on Docker: a recipe with a
base of the model's choosing is refused by the tool before any reviewer sees
it; the corrected recipe builds, carries everything the manifest requires, and
starts. Only the model is scripted.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from orchestrator.core import engine as engine_module  # noqa: E402
from orchestrator.core.engine import OrchestrationEngine  # noqa: E402
from orchestrator.core.task_graph import TaskState  # noqa: E402

AGENT = ROOT / "agent"
SUBJECT = AGENT / "tests" / "fixtures" / "apps" / "flask-hello"
RECORD = AGENT / "tests" / "fixtures" / "artifacts" / "valid.artifact.yaml"
TASKS = [{"task_id": "pkg-001", "title": "package flask-hello", "subsystem": "package",
          "assigned_to": "packager", "dependencies": [],
          "produces": ["package/Dockerfile", "package/PROVENANCE.json"],
          "description": "write the recipe"}]
RECIPE = """FROM {base}
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
CMD ["python", "app.py"]
"""


def _docker_ok() -> bool:
    return bool(shutil.which("docker")) and subprocess.run(
        ["docker", "info"], capture_output=True).returncode == 0


def _manifest() -> dict:
    from artifact_manifest import build_from_artifact
    return json.loads(build_from_artifact(RECORD, "docker", subject=SUBJECT).to_json())


class Model:
    def __init__(self):
        self.reviewed = 0
        self.packager_prompts = []

    async def __call__(self, agent_id, system, messages, tools, tool_executor, **_):
        from package_gate import load_bases
        prompt = messages[0]["content"]
        role = agent_id.split("-")[0]
        if role == "manager":
            return _say(json.dumps(TASKS) if "## Goal" in prompt else "{}")
        if role == "packager":
            self.packager_prompts.append(prompt)
            retry = "Review feedback" in prompt
            base = load_bases()["runtime:python-3.12"] if retry else "python:3.12"
            if retry:
                await tool_executor("read_file", {"path": "package/Dockerfile"})
                await tool_executor("read_file", {"path": "package/PROVENANCE.json"})
            await tool_executor("write_file", {"path": "package/Dockerfile",
                                               "content": RECIPE.format(base=base)})
            await tool_executor("write_file", {"path": "package/PROVENANCE.json",
                                               "content": "[]\n"})
            return _say("wrote the recipe")
        if role == "reviewer":
            self.reviewed += 1
            return _say(json.dumps({"verdict": "approve", "summary": "ok", "issues": []}))
        return _say(json.dumps({"success": True}))


def _say(text):
    return [{"role": "assistant", "content": text}]


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    real = asyncio.sleep

    async def fast(_):
        await real(0)
    monkeypatch.setattr(engine_module.asyncio, "sleep", fast)
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "README.md").write_text("base\n")
    subprocess.run(["git", "init", "-q", "-b", "main", str(ws)], check=True)
    subprocess.run(["git", "-C", str(ws), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(ws), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], check=True)
    return ws


def _engine(ws, manifest):
    return OrchestrationEngine(
        workspace_path=ws, kernel_spec_path=AGENT / "kernel_spec", subject_path=SUBJECT,
        manifest=manifest,
        config={"llm": {"model": "anthropic/scripted"},
                "orchestrator": {"max_iterations": 8, "max_review_rounds": 3},
                "agents": {"developer_count": 1, "reviewer_count": 1, "tester_count": 1},
                "validation": {"composition_checks": False}})


async def test_no_container_manifest_no_packager(workspace, monkeypatch):
    eng = _engine(workspace, {})
    monkeypatch.setattr(eng.client, "send_with_tools", Model())
    await eng.run("x")
    assert "packager" not in eng._agents


@pytest.mark.skipif(not _docker_ok(), reason="no Docker daemon")
async def test_an_unlisted_base_is_refused_by_the_gate_then_the_fix_merges(workspace,
                                                                          monkeypatch):
    eng = _engine(workspace, _manifest())
    model = Model()
    monkeypatch.setattr(eng.client, "send_with_tools", model)
    await eng.run("package the application")

    assert eng.scheduler.status()["packager"]["total"] == 1
    node = eng.task_graph.get_task("pkg-001")
    assert node.state is TaskState.MERGED, node.data.get("failure_reason")
    assert node.review_rounds == 1
    assert "not a listed base" in node.data["review_feedback"][0]["summary"]
    assert model.reviewed == 1, "the reviewer saw only the recipe that built"
    assert "FROM python:3.12-slim@sha256:" in model.packager_prompts[0]
    report = json.loads((workspace / ".auton" / "package-report.json").read_text())
    assert report["ok"] and report["missing"] == [] and report["started"] == "running"
    assert len(report["extras"]) > 0, "extras are measured and reported"


LOOPBACK = """FROM {base}
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
CMD ["python", "-c", "import app; app.app.run(host='127.0.0.1', port=8000)"]
"""


class LoopbackFirst(Model):
    """w22 js_example: the recipe started, and refused every outside connection."""

    async def __call__(self, agent_id, system, messages, tools, tool_executor, **kw):
        if agent_id.startswith("packager"):
            from package_gate import load_bases
            prompt = messages[0]["content"]
            self.packager_prompts.append(prompt)
            retry = "Review feedback" in prompt
            recipe = (RECIPE if retry else LOOPBACK).format(base=load_bases()["runtime:python-3.12"])
            if retry:
                await tool_executor("read_file", {"path": "package/Dockerfile"})
                await tool_executor("read_file", {"path": "package/PROVENANCE.json"})
            await tool_executor("write_file", {"path": "package/Dockerfile", "content": recipe})
            await tool_executor("write_file", {"path": "package/PROVENANCE.json", "content": "[]\n"})
            return _say("wrote the recipe")
        return await super().__call__(agent_id, system, messages, tools, tool_executor, **kw)


@pytest.mark.skipif(not _docker_ok(), reason="no Docker daemon")
async def test_the_gate_runs_the_operators_probe_before_review(workspace, monkeypatch):
    eng = OrchestrationEngine(
        workspace_path=workspace, kernel_spec_path=AGENT / "kernel_spec", subject_path=SUBJECT,
        manifest=_manifest(), probe_path=AGENT / "tests/fixtures/probes/flask-hello.yaml",
        config={"llm": {"model": "anthropic/scripted"},
                "orchestrator": {"max_iterations": 8, "max_review_rounds": 3},
                "agents": {"developer_count": 1, "reviewer_count": 1, "tester_count": 1},
                "validation": {"composition_checks": False}})
    model = LoopbackFirst()
    monkeypatch.setattr(eng.client, "send_with_tools", model)
    await eng.run("package the application")

    node = eng.task_graph.get_task("pkg-001")
    assert node.state is TaskState.MERGED, node.data.get("failure_reason")
    first = node.data["review_feedback"][0]["summary"]
    assert "external probe" in first and "Connection refused" in first
    assert model.reviewed == 1, "the reviewer saw only the recipe that works from outside"
