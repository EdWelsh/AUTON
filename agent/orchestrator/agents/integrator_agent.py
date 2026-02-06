"""Integrator Agent - merges approved branches and ensures coherence."""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.agents.base_agent import Agent, AgentRole, TaskResult
from orchestrator.comms.diff_protocol import TaskMetadata, TaskStatus
from orchestrator.llm.prompts import INTEGRATOR_SYSTEM_PROMPT
from orchestrator.llm.tools import INTEGRATOR_TOOLS

logger = logging.getLogger(__name__)


class IntegratorAgent(Agent):
    """Merges approved branches into main and validates the result.

    The Integrator is the last line of defense against composition issues.
    After each merge, it runs the full test suite to catch regressions.
    """

    def __init__(self, **kwargs):
        super().__init__(
            role=AgentRole.INTEGRATOR,
            system_prompt=INTEGRATOR_SYSTEM_PROMPT,
            tools=INTEGRATOR_TOOLS,
            **kwargs,
        )

    async def merge_approved(self) -> list[dict[str, Any]]:
        """Find and merge all approved branches.

        Returns a list of merge results.
        """
        tasks = TaskMetadata.load_all(self.workspace.path)
        approved = [t for t in tasks if t.status == TaskStatus.APPROVED]

        if not approved:
            logger.info("[%s] No approved branches to merge", self.agent_id)
            return []

        results = []
        for task_meta in approved:
            result = await self.merge_branch(task_meta)
            results.append(result)
            if not result.get("success"):
                logger.warning(
                    "[%s] Merge failed for %s, stopping further merges",
                    self.agent_id, task_meta.task_id,
                )
                break

        return results

    async def merge_branch(self, task_meta: TaskMetadata) -> dict[str, Any]:
        """Merge a single approved branch and validate."""
        logger.info(
            "[%s] Merging %s (branch: %s)",
            self.agent_id, task_meta.task_id, task_meta.branch,
        )

        task = {
            "task_id": f"merge-{task_meta.task_id}",
            "title": f"Merge {task_meta.task_id}",
            "subsystem": task_meta.subsystem,
            "description": f"""Merge the approved branch '{task_meta.branch}' into main.

## Instructions
1. Check out the main branch
2. View the diff of the branch to understand what's being merged
3. Merge the branch into main
4. If there are merge conflicts:
   - For simple conflicts (whitespace, formatting), resolve automatically
   - For semantic conflicts, describe the conflict in your response
5. After merge, build the kernel
6. After build, run the full test suite
7. If tests fail, identify which merge caused the failure

## Task Being Merged
- Task: {task_meta.task_id} - {task_meta.title}
- Subsystem: {task_meta.subsystem}
- Branch: {task_meta.branch}
""",
        }

        # Switch to main before merging
        self.workspace.checkout_main()

        result = await self.execute_task(task)

        # Update task metadata
        if result.success:
            task_meta.status = TaskStatus.MERGED
        else:
            task_meta.status = TaskStatus.BLOCKED
        task_meta.save(self.workspace.path)

        return {
            "task_id": task_meta.task_id,
            "branch": task_meta.branch,
            "success": result.success,
            "summary": result.summary,
            "build_status": result.build_status,
            "test_status": result.test_status,
        }

    async def full_integration_check(self) -> dict[str, Any]:
        """Run a full integration check on the main branch.

        Builds everything, runs all tests, checks for composition issues.
        """
        logger.info("[%s] Running full integration check", self.agent_id)

        self.workspace.checkout_main()

        task = {
            "task_id": "integration-check",
            "title": "Full integration check",
            "subsystem": "all",
            "description": """Run a complete integration check on the main branch.

## Instructions
1. List all kernel source files to see what's been built so far
2. Build the entire kernel
3. Run ALL tests (unit + integration)
4. Boot the kernel in QEMU and verify it reaches a known state
5. Report any failures with detailed analysis

This is the comprehensive check that ensures all merged subsystems
work together correctly.""",
        }

        result = await self.execute_task(task)

        return {
            "success": result.success,
            "summary": result.summary,
            "build_status": result.build_status,
            "test_status": result.test_status,
        }
