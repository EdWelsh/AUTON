"""Agent task scheduler - assigns ready tasks to available agents."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from orchestrator.agents.base_agent import Agent, AgentState
from orchestrator.core.task_graph import TaskGraph, TaskNode, TaskState

logger = logging.getLogger(__name__)


@dataclass
class AgentSlot:
    """Tracks an agent instance and its current assignment."""

    agent: Agent
    current_task: str | None = None
    busy: bool = False


class Scheduler:
    """Assigns tasks from the TaskGraph to available agents.

    Manages a pool of agent instances, tracks which agents are busy,
    and schedules ready tasks based on priority and agent availability.
    """

    def __init__(self, task_graph: TaskGraph):
        self.graph = task_graph
        self._agents: dict[str, list[AgentSlot]] = {
            "developer": [],
            "reviewer": [],
            "tester": [],
            "architect": [],
            "integrator": [],
        }

    def register_agent(self, role: str, agent: Agent) -> None:
        """Register an agent instance in the pool."""
        if role not in self._agents:
            self._agents[role] = []
        self._agents[role].append(AgentSlot(agent=agent))
        logger.info("Registered %s agent: %s", role, agent.agent_id)

    def get_available_agent(self, role: str) -> AgentSlot | None:
        """Get an idle agent of the given role."""
        for slot in self._agents.get(role, []):
            if not slot.busy and slot.agent.state in (AgentState.IDLE, AgentState.DONE):
                return slot
        return None

    def get_assignments(self) -> list[tuple[AgentSlot, TaskNode]]:
        """Match ready tasks to available agents.

        Returns a list of (agent_slot, task_node) pairs to execute.
        """
        ready_tasks = self.graph.get_ready_tasks()
        assignments = []

        for task_node in ready_tasks:
            role = task_node.assigned_to
            slot = self.get_available_agent(role)
            if slot is not None:
                slot.busy = True
                slot.current_task = task_node.task_id
                self.graph.assign_agent(task_node.task_id, slot.agent.agent_id)
                assignments.append((slot, task_node))
                logger.info(
                    "Assigned %s to %s (%s)",
                    task_node.task_id, slot.agent.agent_id, role,
                )

        return assignments

    def release_agent(self, agent_id: str) -> None:
        """Mark an agent as available after completing a task."""
        for slots in self._agents.values():
            for slot in slots:
                if slot.agent.agent_id == agent_id:
                    slot.busy = False
                    slot.current_task = None
                    return

    @property
    def busy_count(self) -> int:
        return sum(
            1 for slots in self._agents.values()
            for slot in slots if slot.busy
        )

    @property
    def idle_count(self) -> int:
        return sum(
            1 for slots in self._agents.values()
            for slot in slots if not slot.busy
        )

    def status(self) -> dict[str, Any]:
        """Get scheduler status."""
        result = {}
        for role, slots in self._agents.items():
            result[role] = {
                "total": len(slots),
                "busy": sum(1 for s in slots if s.busy),
                "idle": sum(1 for s in slots if not s.busy),
                "assignments": {
                    s.agent.agent_id: s.current_task
                    for s in slots if s.busy
                },
            }
        return result
