"""Developer Agent - writes kernel code, builds, tests, and commits."""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.agents.base_agent import Agent, AgentRole, TaskResult
from orchestrator.comms.diff_protocol import TaskMetadata, TaskStatus
from orchestrator.llm.prompts import DEVELOPER_SYSTEM_PROMPT
from orchestrator.llm.tools import DEVELOPER_TOOLS

logger = logging.getLogger(__name__)


class DeveloperAgent(Agent):
    """A Developer agent writes kernel code on a feature branch.

    Multiple Developer agents run in parallel, each working on a different
    subsystem or component. They follow the VibeTensor-style iterative loop:
    write code -> build -> fix errors -> test -> commit.
    """

    def __init__(self, **kwargs):
        super().__init__(
            role=AgentRole.DEVELOPER,
            system_prompt=DEVELOPER_SYSTEM_PROMPT,
            tools=DEVELOPER_TOOLS,
            **kwargs,
        )

    async def implement_task(self, task: dict[str, Any]) -> TaskResult:
        """Implement a coding task on a feature branch.

        1. Creates a feature branch
        2. Reads the spec and existing interfaces
        3. Writes implementation code
        4. Builds and fixes errors iteratively
        5. Runs tests
        6. Commits when passing
        """
        task_id = task["task_id"]
        subsystem = task.get("subsystem", "unknown")
        component = task_id.split("-")[-1] if "-" in task_id else task_id

        logger.info("[%s] Implementing %s", self.agent_id, task_id)

        # Create feature branch
        branch = self.workspace.create_branch(self.agent_id, subsystem, component)

        # Update task metadata
        metadata = TaskMetadata(
            task_id=task_id,
            title=task.get("title", ""),
            subsystem=subsystem,
            agent_id=self.agent_id,
            branch=branch,
            status=TaskStatus.IN_PROGRESS,
            description=task.get("description", ""),
            spec_reference=task.get("spec_reference", ""),
            dependencies=task.get("dependencies", []),
            acceptance_criteria=task.get("acceptance_criteria", []),
        )
        metadata.save(self.workspace.path)

        # Execute the task
        result = await self.execute_task(task)

        # Update metadata with results
        metadata.status = TaskStatus.REVIEW if result.success else TaskStatus.BLOCKED
        metadata.build_status = result.build_status
        metadata.test_status = result.test_status
        metadata.save(self.workspace.path)

        # Request review if successful
        if result.success:
            await self.send_message(
                to_agent="reviewer",
                msg_type="review_request",
                payload={
                    "task_id": task_id,
                    "branch": branch,
                    "summary": result.summary,
                    "files": result.artifacts,
                },
            )

        return result

    async def fix_review_feedback(
        self, task_id: str, feedback: dict[str, Any]
    ) -> TaskResult:
        """Address review feedback and re-submit.

        The reviewer may request changes. This method applies those changes
        and re-submits for review.
        """
        logger.info("[%s] Fixing review feedback for %s", self.agent_id, task_id)

        issues = feedback.get("issues", [])
        issue_text = "\n".join(
            f"- [{i['severity']}] {i['file']}:{i.get('line', '?')}: {i['description']}"
            for i in issues
        )

        task = {
            "task_id": task_id,
            "title": f"Fix review feedback for {task_id}",
            "subsystem": feedback.get("subsystem", "unknown"),
            "description": f"""The reviewer requested changes on your code.

## Review Feedback
{feedback.get('summary', 'No summary')}

## Issues to Fix
{issue_text}

## Instructions
1. Read the files mentioned in the issues
2. Fix each issue
3. Build and test
4. Commit the fixes

Address ALL issues marked as 'critical' or 'warning'. 'nit' issues are optional.""",
            "acceptance_criteria": [
                "All critical issues fixed",
                "All warning issues fixed",
                "Code builds cleanly",
                "Tests pass",
            ],
        }

        return await self.execute_task(task)
