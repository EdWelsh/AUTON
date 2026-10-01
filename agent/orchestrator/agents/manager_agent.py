"""Manager Agent - decomposes goals into tasks and coordinates the team."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from orchestrator.agents.base_agent import Agent, AgentRole, AgentState, TaskResult
from orchestrator.comms.diff_protocol import TaskMetadata, TaskStatus
from orchestrator.comms.message_bus import MessageType
from orchestrator.llm.prompts import build_manager_prompt
from orchestrator.llm.tools import MANAGER_TOOLS

logger = logging.getLogger(__name__)


def _get_prompt(kwargs):
    arch = kwargs.get('arch_profile')
    if arch is None:
        from orchestrator.arch_registry import get_arch_profile
        arch = get_arch_profile("x86_64")
    return build_manager_prompt(arch)



def drop_undeliverable(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop tasks that produce nothing, re-pointing their dependents.

    w11: both authorship runs began with "Read Architecture Specification",
    a task with no deliverable. Its result could only be reviewed as nothing,
    and every later task depended on it. A dependent of a dropped task inherits
    that task's own dependencies, transitively, so the chain stays ordered.
    """
    dropped = {t["task_id"]: list(t.get("dependencies") or [])
               for t in tasks if not t.get("produces")}
    for task_id in dropped:
        logger.warning("Dropping task %s: it lists no file in `produces`", task_id)

    def resolve(dep: str, seen: frozenset = frozenset()) -> list[str]:
        if dep not in dropped:
            return [dep]
        if dep in seen:
            return []
        out: list[str] = []
        for d in dropped[dep]:
            out.extend(resolve(d, seen | {dep}))
        return out

    kept = []
    for t in tasks:
        if t["task_id"] in dropped:
            continue
        deps: list[str] = []
        for d in t.get("dependencies") or []:
            for r in resolve(d):
                if r not in deps:
                    deps.append(r)
        kept.append({**t, "dependencies": deps})
    return kept

def merge_seeds(tasks: list[dict[str, Any]],
                seeds: list[dict[str, Any]] | tuple) -> list[dict[str, Any]]:
    """Seed tasks first, exactly as given; a model task with a seed's id is
    replaced by the seed, because the seed carries the gate that decides it."""
    if not seeds:
        return tasks
    seed_ids = {s["task_id"] for s in seeds}
    replaced = [t["task_id"] for t in tasks if t["task_id"] in seed_ids]
    if replaced:
        logger.warning("Manager rewrote seed task(s) %s; keeping the seeds", replaced)
    return [dict(s) for s in seeds] + [t for t in tasks if t["task_id"] not in seed_ids]


class ManagerAgent(Agent):
    """The Manager decomposes high-level goals into tasks and coordinates agents.

    Workflow:
    1. Reads kernel specs to understand what needs to be built
    2. Creates a task graph with dependencies
    3. Assigns tasks to developer/tester/reviewer agents
    4. Monitors progress and re-plans when needed
    5. Detects Frankenstein composition effects
    """

    # Roles the decomposition prompt offers. The engine adds one only after it
    # registers that role with the scheduler: a role advertised but not
    # registered routes every task it gets to an empty pool (engine.py, w12).
    BASE_ROLES = ("developer", "tester", "architect")

    def __init__(self, **kwargs):
        system_prompt = _get_prompt(kwargs)
        super().__init__(
            role=AgentRole.MANAGER,
            system_prompt=system_prompt,
            tools=MANAGER_TOOLS,
            **kwargs,
        )
        self.assignable_roles: list[str] = list(self.BASE_ROLES)
        self.role_notes: list[str] = []

    def advertise_role(self, role: str, note: str = "") -> None:
        if role not in self.assignable_roles:
            self.assignable_roles.append(role)
        if note:
            self.role_notes.append(note)

    async def decompose_goal(self, goal: str,
                             seed_tasks: list[dict[str, Any]] | tuple = ()) -> list[dict[str, Any]]:
        """Decompose a high-level goal into actionable tasks.

        Sends the goal to Claude, which reads specs and returns a structured
        list of tasks with dependencies.
        """
        self.state = AgentState.THINKING
        logger.info("[%s] Decomposing goal: %s", self.agent_id, goal)

        roles = ", ".join(f'"{r}"' for r in self.assignable_roles)
        notes = "".join(f"{n}\n" for n in self.role_notes)
        if seed_tasks:
            # Seeds come from the manifest handoff (A7) and carry their gates.
            # They are inserted after parsing whatever the model returns, so a
            # model that drops or rewrites one cannot lose it.
            notes += ("- These tasks are already defined and will be included "
                      "exactly as written; do not repeat them, but you may add tasks "
                      "that depend on them: "
                      + ", ".join(f"{t['task_id']} ({t['title']})" for t in seed_tasks)
                      + "\n")
        prompt = f"""## Goal
{goal}

## Instructions
1. Read the kernel architecture specification (use read_spec with subsystem='architecture')
2. Read the relevant specifications (read_spec also takes services/<name>,
   drivers/<name>, mitigations/<name>)
3. Decompose this goal into concrete, ordered tasks with dependencies
4. Each task should be small enough for a single developer agent to complete
5. Include acceptance criteria for each task
6. Reading a specification is part of every task, not a task. Every task must
   create or change at least one file, listed in `produces`; a task that
   produces nothing will be dropped.
{notes}
File each task by calling create_task once per task (preferred). If you cannot,
return the tasks as a JSON array instead. Each task must have:
- task_id: unique identifier (e.g., "boot-001")
- title: short description
- subsystem: which kernel subsystem
- assigned_to: agent role ({roles})
- dependencies: list of task_ids that must complete first
- priority: 1 (highest) to 5 (lowest)
- spec_reference: which spec section to read
- acceptance_criteria: list of conditions for "done"
- description: detailed instructions for the agent
- produces: list of file paths this task creates or changes (at least one)

Return ONLY the JSON array, no other text."""

        messages = [{"role": "user", "content": prompt}]
        self.planned_tasks = []
        result_messages = await self.client.send_with_tools(
            agent_id=self.agent_id,
            system=self.system_prompt,
            messages=messages,
            tools=self.tools,
            tool_executor=self._execute_tool,
        )

        # Tasks filed through create_task come first; a JSON array in the reply
        # is still accepted, and fills in any id the tool calls did not.
        planned = list(self.planned_tasks)
        ids = {t["task_id"] for t in planned}
        parsed = self._parse_tasks(result_messages) if not planned else \
            [t for t in self._parse_tasks_quiet(result_messages) if t.get("task_id") not in ids]
        tasks = merge_seeds(drop_undeliverable(planned + parsed), seed_tasks)
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

    def _parse_tasks_quiet(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """As _parse_tasks, without logging an error: used when create_task
        already planned the work and a JSON array is optional."""
        text = self._extract_final_text(messages)
        try:
            return json.loads(text[text.index("["):text.rindex("]") + 1])
        except (ValueError, json.JSONDecodeError):
            return []

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
