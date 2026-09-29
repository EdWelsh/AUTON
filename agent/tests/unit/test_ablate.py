"""How each capability kind is removed for ablation (A9), without Docker."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from ablate import removal  # noqa: E402

PROBE = {"checks": [{"kind": "http", "port": 8000}]}


def test_a_library_is_deleted_by_soname_including_links():
    line = removal("lib:libssl.so.3", PROBE)
    assert line.startswith("RUN find / -xdev -name libssl.so.3") and "-type l" in line


def test_a_path_and_a_program_are_removed():
    assert removal("path:/etc/ssl/certs", PROBE) == "RUN rm -rf /etc/ssl/certs"
    assert "/usr/local/bin" in removal("exec:git", PROBE)


def test_names_are_shell_quoted():
    assert "'/etc/a b'" in removal("path:/etc/a b", PROBE)


@pytest.mark.parametrize("cap", ["runtime:python-3.12", "dial:tcp/db:5432",
                                 "device:urandom", "env:X"])
def test_kinds_that_cannot_be_removed_by_recipe_say_why(cap):
    outcome, why = removal(cap, PROBE)
    assert outcome == "not-ablatable" and why


def test_a_port_records_whether_the_probe_checks_it():
    assert "does check port 8000" in removal("listen:tcp/8000", PROBE)[1]
    assert "does NOT check port 9000" in removal("listen:tcp/9000", PROBE)[1]


async def test_the_tester_cannot_ablate_without_the_operators_probe(tmp_path):
    from orchestrator.agents.base_agent import Agent, AgentRole
    from orchestrator.arch_registry import get_arch_profile
    from orchestrator.llm.tools import TESTER_TOOLS
    ws = MagicMock()
    ws.path = tmp_path
    agent = Agent(agent_id="tester-01", role=AgentRole.TESTER, system_prompt="t",
                  tools=TESTER_TOOLS, client=MagicMock(), workspace=ws,
                  message_bus=MagicMock(), kernel_spec_path=tmp_path,
                  arch_profile=get_arch_profile("x86_64"))
    out = await agent._execute_tool("run_ablation", {})
    assert "no probe declaration" in out
