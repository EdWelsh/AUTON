"""The reviewer and tester can run the suites that judge the run (w23 G4).

R1's two deviations from the spec were one line each. The swarm's reviewer and
tester approved the code without ever running the frozen suites that failed it.
`run_gate` hands them those suites, as the operator declared them.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from orchestrator.agents.base_agent import Agent, AgentRole
from orchestrator.arch_registry import get_arch_profile
from orchestrator.llm.tools import REVIEWER_TOOLS, TESTER_TOOLS


def _agent(tmp_path, role=AgentRole.TESTER, tools=TESTER_TOOLS, gates=None):
    ws = MagicMock()
    ws.path = tmp_path
    agent = Agent(agent_id="tester-01", role=role, system_prompt="t", tools=tools,
                  client=MagicMock(), workspace=ws, message_bus=MagicMock(),
                  kernel_spec_path=tmp_path, arch_profile=get_arch_profile("x86_64"))
    if gates is not None:
        agent.gate_commands = gates
    return agent


def _names(tools):
    return {t["function"]["name"] for t in tools}


def test_reviewers_and_testers_hold_the_tool_and_developers_cannot_choose_gates():
    assert "run_gate" in _names(REVIEWER_TOOLS) and "run_gate" in _names(TESTER_TOOLS)
    schema = next(t for t in TESTER_TOOLS if t["function"]["name"] == "run_gate")
    assert schema["function"]["parameters"]["properties"] == {}, "no argument to abuse"


async def test_without_declared_gates_it_refuses(tmp_path):
    out = await _agent(tmp_path)._execute_tool("run_gate", {})
    assert out.startswith("Refused") and "no gate suites" in out


async def test_each_gate_runs_against_the_workspace_and_reports_its_exit(tmp_path):
    agent = _agent(tmp_path, gates=[
        'test "$KERNEL_TREE" = "%s" && echo tree-ok' % tmp_path,
        "echo broken; exit 1",
        "exit 2",
    ])
    out = await agent._execute_tool("run_gate", {})
    assert "tree-ok" in out and "[exit 0: pass]" in out
    assert "broken" in out and "[exit 1: generated wrong]" in out
    assert "[exit 2: not generated]" in out


async def test_arguments_cannot_change_what_runs(tmp_path):
    marker = tmp_path / "pwned"
    agent = _agent(tmp_path, gates=["echo fixed"])
    out = await agent._execute_tool("run_gate", {"command": f"touch {marker}", "gate": "x"})
    assert "fixed" in out and not marker.exists()


async def test_a_gate_that_cannot_start_is_reported_not_raised(tmp_path, monkeypatch):
    agent = _agent(tmp_path, gates=["echo hi"])
    monkeypatch.setattr(agent, "GATE_TIMEOUT", 0.01)
    out = await _agent_run_slow(agent)
    assert "timed out" in out


async def _agent_run_slow(agent):
    agent.gate_commands = ["sleep 5"]
    return await agent._execute_tool("run_gate", {})


def test_the_engine_hands_the_declared_gates_to_reviewers_and_testers(tmp_path):
    from orchestrator.core.engine import OrchestrationEngine
    eng = OrchestrationEngine(
        workspace_path=tmp_path, kernel_spec_path=tmp_path,
        config={"llm": {"model": "anthropic/x"}, "agents": {}},
        gate_commands=["tests/kernel/run_mm_test.sh"])
    eng._init_agents()
    holders = [a for k, a in eng._agents.items() if k.startswith(("reviewer", "tester"))]
    assert holders and all(a.gate_commands == ["tests/kernel/run_mm_test.sh"] for a in holders)
