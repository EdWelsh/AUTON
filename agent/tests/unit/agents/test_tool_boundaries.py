"""An agent may use only the tools it was given (w18 live Analyst run).

Dispatch is by tool name, and every role's tools share one dispatcher. On the
first live run the manager — read_spec, list_files, read_file, search_code —
called write_file and wrote the Analyst's record itself, unreviewed. The same
hole left the Analyst's "no shell" a comment rather than a rule.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.agents.base_agent import Agent, AgentRole
from orchestrator.arch_registry import get_arch_profile
from orchestrator.comms.git_workspace import GitWorkspace
from orchestrator.llm.tools import ANALYST_TOOLS, MANAGER_TOOLS


def _agent(ws: GitWorkspace, tools) -> Agent:
    return Agent(agent_id="x-01", role=AgentRole.MANAGER, system_prompt="t", tools=tools,
                 client=MagicMock(), workspace=ws, message_bus=MagicMock(),
                 kernel_spec_path=Path("/nonexistent"), arch_profile=get_arch_profile("x86_64"))


@pytest.fixture
def ws(tmp_path):
    w = GitWorkspace(tmp_path / "ws")
    w.init()
    return w


async def test_the_manager_cannot_write(ws):
    out = await _agent(ws, MANAGER_TOOLS)._execute_tool(
        "write_file", {"path": "analysis/x.yaml", "content": "x"})
    assert out.startswith("Refused: write_file is not one of your tools")
    assert not (ws.path / "analysis/x.yaml").exists()


async def test_the_analyst_has_no_shell(ws, tmp_path):
    sentinel = tmp_path / "ran"
    out = await _agent(ws, ANALYST_TOOLS)._execute_tool(
        "shell", {"command": f"python3 -c \"open('{sentinel}','w')\""})
    assert "Refused" in out and not sentinel.exists()


async def test_a_given_tool_still_works(ws):
    (ws.path / "a.txt").write_text("hi\n")
    assert await _agent(ws, MANAGER_TOOLS)._execute_tool("read_file", {"path": "a.txt"}) == "hi\n"


async def test_an_invented_tool_is_still_told_what_exists(ws):
    out = await _agent(ws, MANAGER_TOOLS)._execute_tool("tftp_server_init", {})
    assert out.startswith("Unknown tool") and "read_file" in out
