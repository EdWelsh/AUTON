"""Analyst Agent - reads a staged application and records what it needs.

Application-to-environment A3. The Analyst's only output is an artifact record
(`agent/tools/artifact_spec.py`): evidence, each fact cited to a file and line
of the staged subject, each capability drawn from a closed index. It proposes;
tools decide. The record is validated before any reviewer sees it
(`syntax_gate.record_errors`), including a check that every quote is really on
the line it cites.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from orchestrator.agents.base_agent import Agent, AgentRole, TaskResult
from orchestrator.comms.git_workspace import SUBJECT_DIR
from orchestrator.llm.prompts import build_analyst_prompt
from orchestrator.llm.tools import ANALYST_TOOLS

logger = logging.getLogger(__name__)

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def _get_prompt(kwargs):
    arch = kwargs.get("arch_profile")
    if arch is None:
        from orchestrator.arch_registry import get_arch_profile
        arch = get_arch_profile("x86_64")
    return build_analyst_prompt(arch)


def vocabulary() -> str:
    """The closed index, as the Analyst sees it in every task."""
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    from artifact_spec import known, load_index

    index = load_index()
    lines = []
    for name, kind in sorted(index.kinds.items()):
        if not kind.enabled:
            continue
        lines.append(f"- {name}: {', '.join(known(name, index))}")
    return "\n".join(lines)


class AnalystAgent(Agent):
    """Reads `.auton/subject/`, writes `analysis/<app>.artifact.yaml`."""

    def __init__(self, **kwargs):
        super().__init__(
            role=AgentRole.ANALYST,
            system_prompt=_get_prompt(kwargs),
            tools=ANALYST_TOOLS,
            **kwargs,
        )
        # Set by the engine once the subject is staged.
        self.subject_hash: str = ""
        self.subject_commit: str | None = None
        self.subject_repo: str = ""

    async def implement_task(self, task: dict[str, Any]) -> TaskResult:
        """Work on a branch of its own, so the record is reviewable — and
        gated — like any other change."""
        component = task["task_id"].split("-")[-1] if "-" in task["task_id"] else task["task_id"]
        earlier = task.get("resume_branch")
        if earlier and self.workspace.branch_exists(earlier):
            self.workspace.checkout(earlier)
            branch = earlier
        else:
            branch = self.workspace.create_branch(self.agent_id, "analysis", component)
        task["resume_branch"] = branch
        self._task_branch = branch
        try:
            return await self.execute_task(task)
        finally:
            self._task_branch = None

    def _format_task_prompt(self, task: dict[str, Any]) -> str:
        subject = (
            f"\n**Subject**: staged read-only at {SUBJECT_DIR}/\n"
            f"- repo: {self.subject_repo or 'unknown'}\n"
            f"- commit: {self.subject_commit or 'none (not a git repository)'}\n"
            f"- tree_hash: {self.subject_hash}\n"
            f"\n**Capability index** (the only names you may use):\n{vocabulary()}\n"
        )
        return super()._format_task_prompt(task) + "\n" + subject
