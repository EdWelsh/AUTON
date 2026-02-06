"""Reviewer Agent - validates code quality, safety, and spec compliance."""

from __future__ import annotations

import json
import logging
from typing import Any

from orchestrator.agents.base_agent import Agent, AgentRole, TaskResult
from orchestrator.comms.diff_protocol import TaskMetadata, TaskStatus
from orchestrator.llm.prompts import REVIEWER_SYSTEM_PROMPT
from orchestrator.llm.tools import REVIEWER_TOOLS

logger = logging.getLogger(__name__)


class ReviewerAgent(Agent):
    """Reviews code diffs from Developer agents.

    Checks for correctness, memory safety, spec compliance, and
    potential composition issues with other subsystems.
    """

    def __init__(self, **kwargs):
        super().__init__(
            role=AgentRole.REVIEWER,
            system_prompt=REVIEWER_SYSTEM_PROMPT,
            tools=REVIEWER_TOOLS,
            **kwargs,
        )

    async def review_branch(self, task_id: str, branch: str) -> dict[str, Any]:
        """Review a developer's feature branch.

        Returns a structured review with verdict (approve/request_changes),
        summary, and list of issues.
        """
        logger.info("[%s] Reviewing branch %s for task %s", self.agent_id, branch, task_id)

        task = {
            "task_id": f"review-{task_id}",
            "title": f"Review code for {task_id}",
            "subsystem": "review",
            "description": f"""Review the code changes on branch '{branch}' for task '{task_id}'.

## Instructions
1. Use git_diff to see the changes on this branch (diff against main)
2. Read the full files that were changed
3. Read the subsystem specification for context
4. Check for:
   - **Correctness**: Does the code do what the spec says?
   - **Memory safety**: No leaks, use-after-free, double-free, buffer overflows
   - **Undefined behavior**: No UB per the C standard
   - **API compliance**: Functions match the header file interfaces
   - **Style**: Follows Linux kernel coding style
   - **Composition risks**: Will this break when combined with other subsystems?

## Output
Return your review as a JSON object:
```json
{{
    "verdict": "approve" or "request_changes",
    "summary": "Brief overall assessment",
    "issues": [
        {{
            "severity": "critical" | "warning" | "nit",
            "file": "path/to/file.c",
            "line": 42,
            "description": "What's wrong and suggested fix"
        }}
    ]
}}
```

Only block with "request_changes" for critical or warning issues.
Approve with nits if issues are minor.""",
        }

        result = await self.execute_task(task)
        review = self._parse_review(result.summary)

        # Update task metadata
        try:
            metadata = TaskMetadata.load(self.workspace.path, task_id)
            if review.get("verdict") == "approve":
                metadata.status = TaskStatus.APPROVED
            else:
                metadata.status = TaskStatus.REJECTED
            metadata.review_comments.append(review)
            metadata.save(self.workspace.path)
        except Exception as e:
            logger.warning("Could not update task metadata: %s", e)

        return review

    def _parse_review(self, text: str) -> dict[str, Any]:
        """Parse a structured review from the agent's text output."""
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            # If we can't parse structured output, create a basic review
            return {
                "verdict": "request_changes",
                "summary": "Could not parse structured review. Raw output: " + text[:500],
                "issues": [],
            }
