"""Architect Agent - makes design decisions and defines subsystem interfaces."""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.agents.base_agent import Agent, AgentRole
from orchestrator.llm.prompts import ARCHITECT_SYSTEM_PROMPT
from orchestrator.llm.tools import ARCHITECT_TOOLS

logger = logging.getLogger(__name__)


class ArchitectAgent(Agent):
    """The Architect defines interfaces, makes design decisions, and writes specs.

    Unlike Developers, the Architect writes header files and documentation,
    not implementation code. It defines the contracts that Developers implement.
    """

    def __init__(self, **kwargs):
        super().__init__(
            role=AgentRole.ARCHITECT,
            system_prompt=ARCHITECT_SYSTEM_PROMPT,
            tools=ARCHITECT_TOOLS,
            **kwargs,
        )

    async def design_subsystem(self, subsystem: str) -> dict[str, Any]:
        """Create the interface design for a kernel subsystem.

        Reads the spec, designs the API, writes header files.
        """
        logger.info("[%s] Designing subsystem: %s", self.agent_id, subsystem)

        task = {
            "task_id": f"arch-{subsystem}",
            "title": f"Design {subsystem} subsystem interface",
            "subsystem": subsystem,
            "description": f"""Design the interface for the {subsystem} kernel subsystem.

1. Read the {subsystem} specification (use read_spec tool)
2. Read the architecture specification for overall context
3. Design the public API as C header files
4. Write the header files to the workspace under kernel/include/
5. Document design decisions as comments in the headers
6. Ensure compatibility with interfaces from other subsystems
7. Commit the header files

The headers should be complete enough that a Developer agent can implement
the subsystem without further guidance.""",
            "acceptance_criteria": [
                f"Header file(s) for {subsystem} written to kernel/include/",
                "All public functions documented with comments",
                "No circular dependencies with other subsystem headers",
                "Types and constants clearly defined",
            ],
        }

        # Create a branch for this design work
        branch = self.workspace.create_branch(self.agent_id, "arch", subsystem)
        result = await self.execute_task(task)
        return {
            "subsystem": subsystem,
            "branch": branch,
            "result": result,
        }

    async def review_integration(self, subsystems: list[str]) -> dict[str, Any]:
        """Review how multiple subsystems integrate and flag conflicts.

        This is the key defense against the Frankenstein composition effect.
        """
        logger.info("[%s] Reviewing integration of: %s", self.agent_id, subsystems)

        subsystem_list = ", ".join(subsystems)
        task = {
            "task_id": "arch-integration-review",
            "title": f"Review integration of {subsystem_list}",
            "subsystem": "cross-cutting",
            "description": f"""Review the integration points between these subsystems: {subsystem_list}

1. Read the header files for each subsystem
2. Read the implementation code for each subsystem
3. Identify potential conflicts:
   - Shared data structures used differently
   - Locking order violations
   - Memory allocation patterns that conflict
   - Interrupt handling conflicts
   - Global state that could cause race conditions
4. Check for the "Frankenstein effect" - subsystems that work in isolation
   but will fail when composed

Output a JSON report with:
- conflicts: list of identified conflicts
- risks: potential issues that need testing
- recommendations: changes needed before merging""",
            "acceptance_criteria": [
                "All cross-subsystem interfaces reviewed",
                "Potential conflicts identified and documented",
                "Recommendations provided for each conflict",
            ],
        }

        return await self.execute_task(task)
