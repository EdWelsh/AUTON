"""Seed tasks from a manifest handoff survive decomposition (A7).

A seed carries the gate that decides it. The manager model may add tasks
around seeds, but cannot drop or rewrite one: they are inserted after parsing.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from orchestrator.agents.manager_agent import merge_seeds
from orchestrator.core import engine as engine_module
from orchestrator.core.engine import OrchestrationEngine
from orchestrator.core.task_graph import TaskState

SPECS = Path(__file__).resolve().parents[3] / "kernel_spec"
SEED = {"task_id": "gen-vmm", "title": "Implement vmm", "subsystem": "mm",
        "assigned_to": "developer", "dependencies": [], "produces": ["kernel/mm/vmm.c"],
        "acceptance_criteria": ["KERNEL_TREE=<workspace> tests/kernel/run_vmm_test.sh exits 0"],
        "description": "implement it", "seed": True}


def test_a_seed_replaces_a_model_task_with_its_id():
    model = [{"task_id": "gen-vmm", "title": "something else", "produces": ["x.c"]},
             {"task_id": "k-1", "title": "other", "produces": ["y.c"]}]
    merged = merge_seeds(model, [SEED])
    assert merged[0] == SEED and [t["task_id"] for t in merged] == ["gen-vmm", "k-1"]


def test_no_seeds_changes_nothing():
    tasks = [{"task_id": "a"}]
    assert merge_seeds(tasks, ()) is tasks


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


async def test_a_manager_that_ignores_the_seed_still_gets_it_run(workspace, monkeypatch):
    real = asyncio.sleep

    async def fast(_):
        await real(0)
    monkeypatch.setattr(engine_module.asyncio, "sleep", fast)
    prompts = []

    async def model(agent_id, system, messages, tools, tool_executor, **_):
        prompt = messages[0]["content"]
        prompts.append((agent_id, prompt))
        if agent_id.startswith("manager"):
            return [{"role": "assistant", "content": "[]" if "## Goal" in prompt else "{}"}]
        if agent_id.startswith("dev"):
            await tool_executor("write_file", {"path": "kernel/mm/vmm.c", "content": "int v;\n"})
            return [{"role": "assistant", "content": "done"}]
        return [{"role": "assistant", "content": json.dumps(
            {"verdict": "approve", "summary": "ok", "issues": [], "success": True})}]

    eng = OrchestrationEngine(
        workspace_path=workspace, kernel_spec_path=SPECS, seed_tasks=[SEED],
        config={"llm": {"model": "anthropic/scripted"},
                "orchestrator": {"max_iterations": 6},
                "agents": {"developer_count": 1, "reviewer_count": 1, "tester_count": 1},
                "validation": {"composition_checks": False}})
    monkeypatch.setattr(eng.client, "send_with_tools", model)
    await eng.run("build the kernel the manifest needs")

    node = eng.task_graph.get_task("gen-vmm")
    assert node is not None, "the seed is in the graph although the model returned []"
    assert node.state is TaskState.MERGED
    dev_prompt = next(p for a, p in prompts if a.startswith("dev"))
    assert "run_vmm_test.sh" in dev_prompt, "the gate reaches the developer"
    manager_prompt = next(p for a, p in prompts if a.startswith("manager"))
    assert "gen-vmm" in manager_prompt
