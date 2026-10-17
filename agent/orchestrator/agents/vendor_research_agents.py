"""The vendor spec agents: the Vendor Scout and the Spec Reader.

The Scout turns "AUTON knows this vendor exists" (the registry) into "AUTON knows
what this vendor publishes" (a proposed vendors.yaml entry). The Reader turns a
fetched document into records that cite their page. Both write only into the
run's workspace (hardware/proposals/, hardware/derived/), which is a testing area;
nothing reaches agent/hardware/ until a person merges a checked record.
"""

from __future__ import annotations

from typing import Any

from orchestrator.agents.base_agent import Agent, AgentRole, TaskResult
from orchestrator.llm.prompts import build_spec_reader_prompt, build_vendor_scout_prompt
from orchestrator.llm.tools import SPEC_READER_TOOLS, VENDOR_SCOUT_TOOLS


def _arch(kwargs):
    arch = kwargs.get("arch_profile")
    if arch is None:
        from orchestrator.arch_registry import get_arch_profile
        arch = get_arch_profile("x86_64")
    return arch


class _BranchingAgent(Agent):
    """Each task on its own branch, so its record is reviewed like any change."""

    area = "hardware"

    async def implement_task(self, task: dict[str, Any]) -> TaskResult:
        component = task["task_id"].split("-")[-1] if "-" in task["task_id"] else task["task_id"]
        earlier = task.get("resume_branch")
        if earlier and self.workspace.branch_exists(earlier):
            self.workspace.checkout(earlier)
            branch = earlier
        else:
            branch = self.workspace.create_branch(self.agent_id, self.area, component)
        task["resume_branch"] = branch
        self._task_branch = branch
        try:
            return await self.execute_task(task)
        finally:
            self._task_branch = None


class VendorScoutAgent(_BranchingAgent):
    def __init__(self, **kwargs):
        super().__init__(role=AgentRole.VENDOR_SCOUT,
                         system_prompt=build_vendor_scout_prompt(_arch(kwargs)),
                         tools=VENDOR_SCOUT_TOOLS, **kwargs)
        self.fetch_hosts: tuple[str, ...] = ()


class SpecReaderAgent(_BranchingAgent):
    def __init__(self, **kwargs):
        super().__init__(role=AgentRole.SPEC_READER,
                         system_prompt=build_spec_reader_prompt(_arch(kwargs)),
                         tools=SPEC_READER_TOOLS, **kwargs)
