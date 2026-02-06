"""Manager Agent - decomposes goals into tasks and coordinates the team."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from orchestrator.agents.base_agent import Agent, AgentRole, AgentState, TaskResult
from orchestrator.comms.diff_protocol import TaskMetadata, TaskStatus
from orchestrator.comms.message_bus import MessageType
from orchestrator.llm.prompts import MANAGER_SYSTEM_PROMPT
from orchestrator.llm.tools import MANAGER_TOOLS

logger = logging.getLogger(__name__)


class ManagerAgent(Agent):
    """The Manager decomposes high-level goals into tasks and coordinates agents.

    Workflow:
    1. Reads kernel specs to understand what needs to be built
    2. Creates a task graph with dependencies
    3. Assigns tasks to developer/tester/reviewer agents
    4. Monitors progress and re-plans when needed
    5. Detects Frankenstein composition effects
    """

    def __init__(self, **kwargs):
        super().__init__(
            role=AgentRole.MANAGER,
            system_prompt=MANAGER_SYSTEM_PROMPT,
            tools=MANAGER_TOOLS,
            **kwargs,
        )

    async def decompose_goal(self, goal: str) -> list[dict[str, Any]]:
        """Decompose a high-level goal into actionable tasks.

        Sends the goal to Claude, which reads specs and returns a structured
        list of tasks with dependencies.
        """
        self.state = AgentState.THINKING
        logger.info("[%s] Decomposing goal: %s", self.agent_id, goal)

        prompt = f"""## Goal
{goal}

## Instructions
1. Read the kernel architecture specification (use read_spec with subsystem='architecture')
2. Read the relevant subsystem specifications
3. Decompose this goal into concrete, ordered tasks with dependencies
4. Each task should be small enough for a single developer agent to complete
5. Include acceptance criteria for each task

Return the tasks as a JSON array. Each task must have:
- task_id: unique identifier (e.g., "boot-001")
- title: short description
- subsystem: which kernel subsystem
- assigned_to: agent role ("developer", "tester", "architect")
- dependencies: list of task_ids that must complete first
- priority: 1 (highest) to 5 (lowest)
- spec_reference: which spec section to read
- acceptance_criteria: list of conditions for "done"
- description: detailed instructions for the agent

Return ONLY the JSON array, no other text."""

        messages = [{"role": "user", "content": prompt}]
        result_messages = await self.client.send_with_tools(
            agent_id=self.agent_id,
            system=self.system_prompt,
            messages=messages,
            tools=self.tools,
            tool_executor=self._execute_tool,
        )

        # Parse tasks from the response
        tasks = self._parse_tasks(result_messages)
        self.state = AgentState.DONE

        # Save task metadata
        for task in tasks:
            metadata = TaskMetadata(
                task_id=task["task_id"],
                title=task["title"],
                subsystem=task["subsystem"],
                agent_id="unassigned",
                branch="",
                status=TaskStatus.PENDING,
                description=task.get("description", ""),
                spec_reference=task.get("spec_reference", ""),
                dependencies=task.get("dependencies", []),
                acceptance_criteria=task.get("acceptance_criteria", []),
            )
            metadata.save(self.workspace.path)

        logger.info("[%s] Created %d tasks", self.agent_id, len(tasks))
        return tasks

    async def assess_progress(self) -> dict[str, Any]:
        """Assess overall project progress and identify issues.

        Returns a status report with recommendations.
        """
        self.state = AgentState.THINKING

        # Load all task metadata
        tasks = TaskMetadata.load_all(self.workspace.path)
        branch_status = self.workspace.get_branch_status()

        status_summary = self._build_status_summary(tasks, branch_status)

        prompt = f"""## Project Status Assessment

{status_summary}

## Instructions
Analyze the current project status and provide:
1. Overall progress percentage
2. Blocked tasks and why they're blocked
3. Potential Frankenstein composition risks (subsystems that might conflict)
4. Recommended next actions
5. Any tasks that should be re-prioritized

Return a JSON object with these fields:
- progress_pct: number 0-100
- blocked_tasks: list of task_ids with reasons
- composition_risks: list of risk descriptions
- next_actions: list of recommended actions
- reprioritize: list of {{task_id, new_priority, reason}}
"""

        messages = [{"role": "user", "content": prompt}]
        result_messages = await self.client.send_with_tools(
            agent_id=self.agent_id,
            system=self.system_prompt,
            messages=messages,
            tools=self.tools,
            tool_executor=self._execute_tool,
        )

        self.state = AgentState.DONE
        return self._parse_json_response(result_messages)

    def _parse_tasks(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extract task list from Claude's response."""
        text = self._extract_final_text(messages)
        # Try to find JSON in the response
        try:
            # Look for JSON array in the text
            start = text.index("[")
            end = text.rindex("]") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError) as e:
            logger.error("[%s] Failed to parse tasks: %s", self.agent_id, e)
            return []

    def _parse_json_response(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Extract JSON object from Claude's response."""
        text = self._extract_final_text(messages)
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            return {"error": "Failed to parse response", "raw": text}

    def _build_status_summary(
        self, tasks: list[TaskMetadata], branches: dict
    ) -> str:
        """Build a text summary of project status for Claude."""
        lines = ["### Tasks"]
        for t in tasks:
            lines.append(
                f"- [{t.status.value}] {t.task_id}: {t.title} "
                f"(subsystem={t.subsystem}, deps={t.dependencies})"
            )

        lines.append("\n### Branches")
        for name, info in branches.items():
            lines.append(f"- {name}: {info['ahead']} commits ahead, last: {info['last_commit']}")

        return "\n".join(lines)
