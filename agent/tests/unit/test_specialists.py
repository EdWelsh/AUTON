"""Specialist agents: defined as data, registered and advertised together, and their
checklists reach the reviewer for the files a change touches."""
from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.agents import specialists as sp

AGENT = Path(__file__).resolve().parents[2]


def test_every_specialist_names_specs_that_exist():
    specs = sp.load()
    assert len(specs) >= 20
    ids = {s.id for s in specs}
    for must in ("boot", "cpu", "memory", "interrupts", "scheduler", "smp", "syscalls",
                 "devices", "filesystems", "networking", "security", "toolchain", "slm"):
        assert must in ids


def test_a_missing_spec_is_refused(tmp_path):
    (tmp_path / "subsystems").mkdir()
    y = tmp_path / "specialists.yaml"
    y.write_text("specialists:\n  - {id: x, title: X, specs: [nope], files: ['a'], "
                 "focus: f, checklist: [c]}\n")
    with pytest.raises(sp.SpecialistError, match="does not exist"):
        sp.load(y)


def test_checklists_follow_the_files_changed():
    specs = sp.load()
    text = sp.checklists_for(["kernel/mm/pmm.c"], specs)
    assert "phys_to_virt" in text and "Network stack" not in text
    assert sp.checklists_for(["README.md"], specs) == ""


def test_select_refuses_an_unknown_id():
    with pytest.raises(sp.SpecialistError, match="unknown"):
        sp.select(sp.load(), ["memory", "telepathy"])
    assert sp.select(sp.load(), False) == ()


def test_the_prompt_carries_the_specialty():
    mem = next(s for s in sp.load() if s.id == "memory")
    assert "Physical and virtual memory" in mem.prompt_section()
    assert mem.pool == "memory_specialist"


def _engine(tmp_path, specialists):
    from orchestrator.core.engine import OrchestrationEngine
    eng = OrchestrationEngine(
        workspace_path=tmp_path / "ws", kernel_spec_path=AGENT / "kernel_spec",
        config={"llm": {"model": "anthropic/scripted"},
                "agents": {"developer_count": 1, "reviewer_count": 1, "tester_count": 1,
                           "specialists": specialists},
                "validation": {"composition_checks": False}})
    eng.workspace.init()
    eng._init_agents()
    return eng


def test_specialists_are_constructed_registered_and_advertised(tmp_path):
    eng = _engine(tmp_path, ["memory", "cpu"])
    status = eng.scheduler.status()
    for pool in ("memory_specialist", "cpu_specialist"):
        assert status[pool]["total"] == 1, "registered"
        assert pool in eng._agents["manager"].assignable_roles, "advertised"
    agent = eng._agents["memory_specialist"]
    assert "Your specialty: Physical and virtual memory" in agent.system_prompt
    reviewer = eng._agents["reviewer-01"]
    assert {s.id for s in reviewer.specialties} == {"memory", "cpu"}


def test_without_the_setting_nothing_changes(tmp_path):
    eng = _engine(tmp_path, None)
    assert not any(k.endswith("_specialist") for k in eng._agents)
    assert eng._agents["reviewer-01"].specialties == ()
