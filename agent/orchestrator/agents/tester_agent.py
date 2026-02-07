"""Tester Agent - writes tests, runs builds, validates kernel behavior."""

from __future__ import annotations

import json
import logging
from typing import Any

from orchestrator.agents.base_agent import Agent, AgentRole, TaskResult
from orchestrator.llm.prompts import build_tester_prompt
from orchestrator.llm.tools import TESTER_TOOLS

logger = logging.getLogger(__name__)


def _get_prompt(kwargs):
    arch = kwargs.get('arch_profile')
    if arch is None:
        from orchestrator.arch_registry import get_arch_profile
        arch = get_arch_profile("x86_64")
    return build_tester_prompt(arch)


class TesterAgent(Agent):
    """Writes and runs tests for kernel subsystems.

    Tests range from unit tests (individual functions) to integration tests
    (booting the kernel in QEMU and checking behavior).
    """

    def __init__(self, **kwargs):
        system_prompt = _get_prompt(kwargs)
        super().__init__(
            role=AgentRole.TESTER,
            system_prompt=system_prompt,
            tools=TESTER_TOOLS,
            **kwargs,
        )

    async def write_tests(self, subsystem: str) -> TaskResult:
        """Write tests for a kernel subsystem."""
        logger.info("[%s] Writing tests for %s", self.agent_id, subsystem)

        branch = self.workspace.create_branch(self.agent_id, "test", subsystem)

        task = {
            "task_id": f"test-write-{subsystem}",
            "title": f"Write tests for {subsystem}",
            "subsystem": subsystem,
            "description": f"""Write comprehensive tests for the {subsystem} kernel subsystem.

## Instructions
1. Read the {subsystem} specification (use read_spec)
2. Read the implementation code
3. Write unit tests that cover:
   - Normal operation (happy path)
   - Edge cases (empty input, max values, null pointers)
   - Error conditions (out of memory, invalid arguments)
   - Stress scenarios (rapid alloc/free cycles, concurrent access)
4. Write integration tests if applicable (test interaction with other subsystems)
5. Tests should output results to serial console:
   ```
   [TEST] test_name: PASS
   [TEST] test_name: FAIL - expected X got Y
   ```
6. Place test files in tests/{subsystem}/
7. Build and verify tests compile
8. Commit test files

Focus on tests that will catch real bugs, not trivial assertions.""",
            "acceptance_criteria": [
                f"Test files created in tests/{subsystem}/",
                "Tests compile without errors",
                "At least 5 meaningful test cases per major function",
                "Edge cases and error conditions covered",
            ],
        }

        return await self.execute_task(task)

    async def run_test_suite(self, subsystem: str | None = None) -> dict[str, Any]:
        """Run the test suite and return structured results."""
        logger.info("[%s] Running tests for %s", self.agent_id, subsystem or "all")

        target = subsystem or "all"
        task = {
            "task_id": f"test-run-{target}",
            "title": f"Run tests for {target}",
            "subsystem": target,
            "description": f"""Run the test suite for {target}.

## Instructions
1. Build the kernel (use build_kernel)
2. Run the tests (use run_test with test_name='{target}')
3. Parse the output for PASS/FAIL results
4. If any tests fail, investigate the failure:
   - Read the relevant source code
   - Identify the root cause
   - Determine if it's a test bug or implementation bug

Return results as JSON:
```json
{{
    "total": 10,
    "passed": 8,
    "failed": 2,
    "failures": [
        {{
            "test": "test_name",
            "expected": "...",
            "actual": "...",
            "analysis": "Root cause explanation"
        }}
    ],
    "build_status": "success" or "failed"
}}
```""",
        }

        result = await self.execute_task(task)
        return self._parse_test_results(result.summary)

    async def composition_test(self, subsystems: list[str]) -> dict[str, Any]:
        """Test the composition of multiple subsystems together.

        This is the key test for detecting the Frankenstein effect.
        """
        sub_list = ", ".join(subsystems)
        logger.info("[%s] Composition test: %s", self.agent_id, sub_list)

        task = {
            "task_id": f"test-compose-{'_'.join(subsystems)}",
            "title": f"Composition test: {sub_list}",
            "subsystem": "integration",
            "description": f"""Test the composition of these subsystems working together: {sub_list}

## Instructions
1. Build the kernel with all subsystems included
2. Boot the kernel in QEMU
3. Exercise each subsystem in sequence
4. Exercise subsystems in combination:
   - Allocate memory while scheduling tasks
   - Send IPC messages while handling interrupts
   - Run multiple operations concurrently
5. Check for:
   - Deadlocks (kernel hangs)
   - Memory corruption (unexpected values)
   - Race conditions (inconsistent results)
   - Performance degradation (operations much slower than in isolation)

This is the most important test. The "Frankenstein effect" means
subsystems that pass all tests individually can fail catastrophically
when composed. Look for subtle interactions.""",
        }

        result = await self.execute_task(task)
        return self._parse_test_results(result.summary)

    def _parse_test_results(self, text: str) -> dict[str, Any]:
        """Parse test results from agent output."""
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            return {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "failures": [],
                "raw_output": text[:1000],
                "parse_error": True,
            }
