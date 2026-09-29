"""Packager Agent - writes the recipe for what a validated manifest names.

Application-to-environment A8. A separate role rather than a grown Integrator:
the Integrator merges branches, and a package that fails to build must not
block a merge. The recipe is decided by `agent/tools/package_gate.py` before
any reviewer sees it — base, build, inventory, start.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from orchestrator.agents.base_agent import Agent, AgentRole, TaskResult
from orchestrator.llm.prompts import build_packager_prompt
from orchestrator.llm.tools import PACKAGER_TOOLS

logger = logging.getLogger(__name__)

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def _get_prompt(kwargs):
    arch = kwargs.get("arch_profile")
    if arch is None:
        from orchestrator.arch_registry import get_arch_profile
        arch = get_arch_profile("x86_64")
    return build_packager_prompt(arch)


class PackagerAgent(Agent):
    """Writes package/Dockerfile and package/PROVENANCE.json on its own branch."""

    def __init__(self, **kwargs):
        super().__init__(role=AgentRole.PACKAGER, system_prompt=_get_prompt(kwargs),
                         tools=PACKAGER_TOOLS, **kwargs)
        self.manifest: dict = {}

    async def implement_task(self, task: dict[str, Any]) -> TaskResult:
        component = task["task_id"].split("-")[-1] if "-" in task["task_id"] else task["task_id"]
        earlier = task.get("resume_branch")
        if earlier and self.workspace.branch_exists(earlier):
            self.workspace.checkout(earlier)
            branch = earlier
        else:
            branch = self.workspace.create_branch(self.agent_id, "package", component)
        task["resume_branch"] = branch
        self._task_branch = branch
        try:
            return await self.execute_task(task)
        finally:
            self._task_branch = None

    def _format_task_prompt(self, task: dict[str, Any]) -> str:
        if str(TOOLS) not in sys.path:
            sys.path.insert(0, str(TOOLS))
        from package_gate import load_bases

        app = self.manifest.get("application") or {}
        runtime = app.get("runtime", "?")
        base = load_bases().get(runtime, "(none listed: the gate will refuse)")
        extra = (
            f"\n**Application**: {app.get('name', '?')} on {app.get('substrate', '?')}\n"
            f"- runtime: {runtime} -> FROM {base}\n"
            f"- requires: {', '.join(app.get('requires') or []) or 'nothing beyond the runtime'}\n"
            f"- assumptions: {'; '.join(self.manifest.get('assumptions') or []) or 'none'}\n"
            f"\nThe full manifest is at .auton/manifest.json; the application at .auton/subject/.\n"
        )
        return super()._format_task_prompt(task) + "\n" + extra
