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


def _ws(tmp_path, requires, recipe=None):
    import json
    from package_gate import load_bases
    ws = tmp_path / "ws"
    (ws / ".auton").mkdir(parents=True)
    (ws / "package").mkdir()
    m = {"application": {"runtime": "runtime:python-3.12", "requires": requires}}
    (ws / ".auton" / "manifest.json").write_text(json.dumps(m))
    (ws / "package" / "Dockerfile").write_text(
        recipe or f"FROM {load_bases()['runtime:python-3.12']}\n")
    probe = tmp_path / "probe.yaml"
    probe.write_text("checks: [{kind: http, port: 80}]\n")
    return ws, probe


def test_a_crafted_requirement_never_reaches_a_dockerfile(tmp_path):
    """w18 review H2: shlex.quote protects the shell, not the Dockerfile parser;
    a newline in a name would start a new RUN."""
    from ablate import ablate
    from app_probe import ProbeError
    ws, probe = _ws(tmp_path, ["lib:x\nRUN touch /pwned"])
    with pytest.raises(ProbeError, match="outside the index"):
        ablate(ws, probe)


def test_a_rewritten_manifest_is_refused(tmp_path):
    from ablate import ablate
    from app_probe import ProbeError
    ws, probe = _ws(tmp_path, ["lib:libssl.so.3"])
    with pytest.raises(ProbeError, match="changed after the engine wrote it"):
        ablate(ws, probe, manifest_sha256="0" * 64)


def test_a_recipe_the_gate_would_refuse_is_not_built(tmp_path):
    from ablate import ablate
    from app_probe import ProbeError
    ws, probe = _ws(tmp_path, ["lib:libssl.so.3"], recipe="FROM ubuntu:24.04\n")
    with pytest.raises(ProbeError, match="package gate would pass"):
        ablate(ws, probe)


def test_removal_as_root_restores_the_final_user():
    from ablate import _as_root
    out = _as_root("FROM x\nUSER app\n", "RUN rm -f /a")
    assert out.endswith("USER root\nRUN rm -f /a\nUSER app\n")


def test_a_system_directory_is_too_broad_to_ablate():
    assert removal("path:/etc", PROBE)[0] == "not-ablatable"
