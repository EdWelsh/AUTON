"""The time budget pauses a real process, through the same `auton_timeout` the
run script uses, with coreutils `timeout` and with the shell fallback.

In-process tests cannot show this: the signal has to come from outside, arrive
while a model call is in flight, and leave the work committed before the grace
period ends.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
AGENT = ROOT / "agent"

DRIVER = textwrap.dedent('''
    import asyncio, json, sys
    from pathlib import Path
    sys.path.insert(0, {agent!r})
    from orchestrator.core.engine import OrchestrationEngine

    TASKS = [{{"task_id": "k-001", "title": "add a", "subsystem": "lib",
               "assigned_to": "developer", "dependencies": [],
               "produces": ["kernel/lib/a.c"], "description": "write a"}}]

    async def model(agent_id, system, messages, tools, tool_executor, **_):
        if agent_id.startswith("manager"):
            return [{{"role": "assistant", "content": json.dumps(TASKS)}}]
        if agent_id.startswith("dev"):
            await tool_executor("write_file", {{"path": "kernel/lib/a.c",
                                               "content": "int a; /* half */\\n"}})
            print("DEV WROTE", flush=True)
            await asyncio.sleep(3600)          # a model call still in flight
        return [{{"role": "assistant", "content": json.dumps({{"success": True}})}}]

    eng = OrchestrationEngine(
        workspace_path=Path({ws!r}), kernel_spec_path=Path({specs!r}),
        config={{"llm": {{"model": "anthropic/scripted"}},
                 "agents": {{"developer_count": 1}},
                 "validation": {{"composition_checks": False}}}})
    eng.client.send_with_tools = model
    result = asyncio.run(eng.run("write a"))
    print("RESULT", json.dumps({{"paused": result.get("paused")}}), flush=True)
    sys.exit(75 if result.get("paused") else 1)
''')


def _git(ws, *args):
    return subprocess.run(["git", "-C", str(ws), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM delivery is POSIX-only")
@pytest.mark.parametrize("timeout_bin", ["real", "shim"])
def test_the_budget_pauses_a_live_run(tmp_path, timeout_bin):
    real = shutil.which("timeout") or shutil.which("gtimeout")
    if timeout_bin == "real" and not real:
        pytest.skip("no coreutils timeout on this host")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "README.md").write_text("base\n")
    subprocess.run(["git", "init", "-q", "-b", "main", str(ws)], check=True)
    _git(ws, "add", "-A")
    subprocess.run(["git", "-C", str(ws), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], check=True)
    driver = tmp_path / "driver.py"
    driver.write_text(DRIVER.format(agent=str(AGENT), ws=str(ws),
                                    specs=str(AGENT / "kernel_spec")))

    timeout_env = real if timeout_bin == "real" else ""
    script = (f'source "{ROOT}/scripts/lib/toolchain.sh"; TIMEOUT_BIN="{timeout_env}"; '
              f'AUTON_KILL_AFTER=20 auton_timeout 6 "{sys.executable}" "{driver}"')
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                         timeout=60)

    assert "DEV WROTE" in out.stdout, out.stdout + out.stderr
    assert out.returncode == 124, "the budget fired"
    assert '"paused": true' in out.stdout, "and the run paused inside the grace\n" + out.stderr
    state = json.loads((ws / ".auton" / "state.json").read_text())
    assert state["phase"] == "paused"
    branch = next(n["data"]["resume_branch"] for n in state["graph"])
    assert "/* half */" in _git(ws, "show", f"{branch}:kernel/lib/a.c")
