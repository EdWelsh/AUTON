"""The vendor agents write only their own output directory (w26 review #11)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from orchestrator.agents.vendor_research_agents import SpecReaderAgent, VendorScoutAgent


def _agent(cls, tmp_path):
    ws = SimpleNamespace(path=tmp_path, write_file=lambda p, c: None, edit_file=lambda *a: None)
    return cls(agent_id="a-01", client=None, workspace=ws, message_bus=None,
               kernel_spec_path=tmp_path)


def _call(agent, tool, path):
    return asyncio.run(agent._execute_tool(tool, {"path": path, "content": "x", "old": "a", "new": "b"}))


def test_the_scout_cannot_write_outside_its_proposals(tmp_path):
    scout = _agent(VendorScoutAgent, tmp_path)
    for path in ("kernel/main.c", "hardware/derived/x.yaml", "hardware/proposals/../../kernel/x.c"):
        assert _call(scout, "write_file", path).startswith("Refused"), path
        assert _call(scout, "edit_file", path).startswith("Refused"), path


def test_the_scout_can_write_its_proposal(tmp_path):
    scout = _agent(VendorScoutAgent, tmp_path)
    assert _call(scout, "write_file", "hardware/proposals/intel.yaml").startswith("Written")


def test_the_reader_writes_only_derived_records(tmp_path):
    reader = _agent(SpecReaderAgent, tmp_path)
    assert _call(reader, "write_file", "hardware/proposals/x.yaml").startswith("Refused")
    assert _call(reader, "write_file", "hardware/derived/doc-1.yaml").startswith("Written")
