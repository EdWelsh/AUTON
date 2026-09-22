"""Reviewer Agent - validates code quality, safety, and spec compliance."""

from __future__ import annotations

import json
import logging
from typing import Any

from orchestrator.agents.base_agent import Agent, AgentRole, TaskResult
from orchestrator.comms.diff_protocol import TaskMetadata, TaskStatus
from orchestrator.llm.prompts import build_reviewer_prompt
from orchestrator.llm.tools import REVIEWER_TOOLS

logger = logging.getLogger(__name__)


def _get_prompt(kwargs):
    arch = kwargs.get('arch_profile')
    if arch is None:
        from orchestrator.arch_registry import get_arch_profile
        arch = get_arch_profile("x86_64")
    return build_reviewer_prompt(arch)



# A review prompt carries the whole diff; past this it is truncated, and says so.
MAX_DIFF_CHARS = 60_000


def ground_review(review: dict[str, Any], changed: list[str]) -> dict[str, Any]:
    """A rejection must point at the change it rejects.

    `request_changes` whose blocking issues name no changed file is not
    feedback an author can act on: it is a review of code that is not there.
    It is downgraded to approve, with the unfounded text kept in the summary so
    the log still shows what the model said.
    """
    if review.get("verdict") != "request_changes":
        return review
    blocking = [i for i in review.get("issues", [])
                if i.get("severity") in ("critical", "warning", None)]
    grounded = [i for i in blocking if i.get("file") in changed]
    if grounded:
        return {**review, "issues": grounded + [
            i for i in review.get("issues", []) if i not in blocking]}
    logger.warning("Rejection cites no changed file (changed: %s); treating as approve: %s",
                   changed, review.get("summary", ""))
    return {**review, "verdict": "approve",
            "summary": f"unfounded rejection discarded: {review.get('summary', '')}"}

class ReviewerAgent(Agent):
    """Reviews code diffs from Developer agents.

    Checks for correctness, memory safety, spec compliance, and
    potential composition issues with other subsystems.
    """

    def __init__(self, **kwargs):
        system_prompt = _get_prompt(kwargs)
        super().__init__(
            role=AgentRole.REVIEWER,
            system_prompt=system_prompt,
            tools=REVIEWER_TOOLS,
            **kwargs,
        )

    async def review_branch(self, task_id: str, branch: str,
                            task_brief: str = "") -> dict[str, Any]:
        """Review a developer's feature branch.

        Returns a structured review with verdict (approve/request_changes),
        summary, and list of issues.

        The diff is put in the prompt rather than left for the model to fetch.
        On w12's first live run the developer's change was exactly right (one
        comment line) and the reviewer, which never called git_diff, rejected
        it three times over a `kmath_add` function that exists nowhere.
        """
        logger.info("[%s] Reviewing branch %s for task %s", self.agent_id, branch, task_id)
        diff_text, changed = self.workspace.branch_diff(branch)
        if len(diff_text) > MAX_DIFF_CHARS:
            diff_text = (diff_text[:MAX_DIFF_CHARS]
                         + f"\n[... diff truncated at {MAX_DIFF_CHARS} characters ...]")

        task = {
            "task_id": f"review-{task_id}",
            "title": f"Review code for {task_id}",
            "subsystem": "review",
            "description": f"""Review the code changes on branch '{branch}' for task '{task_id}'.

## What the task asked for
{task_brief or "(no description given)"}

## The complete change (git diff main...{branch})
Files changed: {", ".join(changed) or "(none)"}

```diff
{diff_text}
```

## Instructions
1. Review ONLY the change above. Do not describe code that is not in it.
2. Read the full changed files if you need their context
3. Read the relevant specification for context
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

Only block with "request_changes" for critical or warning issues, and every
such issue must name a file from "Files changed" above.
Approve with nits if issues are minor.""",
        }

        result = await self.execute_task(task)
        review = ground_review(self._parse_review(result.summary), changed)

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
