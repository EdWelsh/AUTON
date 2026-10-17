"""The Packager is constructed, registered and advertised together, or not at all (w12 rule)."""
from __future__ import annotations

from pathlib import Path

from orchestrator.core.engine import OrchestrationEngine

SPECS = Path(__file__).resolve().parents[3] / "kernel_spec"


def _engine(tmp_path, manifest):
    eng = OrchestrationEngine(workspace_path=tmp_path / "ws", kernel_spec_path=SPECS,
                              manifest=manifest,
                              config={"llm": {"model": "anthropic/scripted"},
                                      "agents": {"developer_count": 1}})
    eng.workspace.init()
    eng._init_agents()
    return eng


def test_a_docker_manifest_brings_a_registered_advertised_packager(tmp_path):
    eng = _engine(tmp_path, {"application": {"name": "app", "substrate": "docker"}})
    assert "packager" in eng._agents
    assert eng.scheduler.status()["packager"]["total"] == 1
    assert "packager" in eng._agents["manager"].assignable_roles


def test_no_manifest_no_packager_anywhere(tmp_path):
    eng = _engine(tmp_path, None)
    assert "packager" not in eng._agents
    assert "packager" not in eng._agents["manager"].assignable_roles
