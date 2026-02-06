"""Composition validation - detects the Frankenstein effect across subsystems."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orchestrator.validation.build_validator import BuildValidator
from orchestrator.validation.test_validator import TestValidator

logger = logging.getLogger(__name__)


@dataclass
class CompositionIssue:
    subsystems: list[str]
    severity: str  # "critical", "warning", "info"
    description: str
    evidence: str = ""


@dataclass
class CompositionResult:
    success: bool
    issues: list[CompositionIssue] = field(default_factory=list)
    build_ok: bool = False
    unit_tests_ok: bool = False
    integration_tests_ok: bool = False
    summary: str = ""


class CompositionValidator:
    """Detects the Frankenstein composition effect.

    From VibeTensor: "Correctness-first autograd and dispatch design can
    introduce serialization points that starve otherwise efficient backend
    kernels." Locally correct subsystems interact to yield globally
    suboptimal or incorrect behavior.

    This validator:
    1. Builds the full kernel with all subsystems
    2. Runs unit tests for each subsystem individually
    3. Runs integration tests that exercise multiple subsystems together
    4. Compares results to detect composition failures
    """

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.build_validator = BuildValidator(workspace_path)
        self.test_validator = TestValidator(workspace_path)

    async def validate(self, subsystems: list[str] | None = None) -> CompositionResult:
        """Run full composition validation."""
        issues = []

        # Step 1: Full build
        logger.info("Composition check: building full kernel")
        build_result = await self.build_validator.build()
        if not build_result.success:
            return CompositionResult(
                success=False,
                build_ok=False,
                summary=f"Build failed: {build_result.stderr[:500]}",
            )

        # Step 2: Run unit tests
        logger.info("Composition check: running unit tests")
        unit_result = await self.test_validator.run_tests()

        # Step 3: Run integration tests
        logger.info("Composition check: running integration tests")
        integration_result = await self.test_validator.run_tests(
            kernel_image=str(self.workspace_path / "build" / "kernel-integration.bin")
        )

        # Step 4: Analyze for composition issues
        if unit_result.success and not integration_result.success:
            # Classic Frankenstein effect: unit tests pass but integration fails
            issues.append(CompositionIssue(
                subsystems=subsystems or ["unknown"],
                severity="critical",
                description=(
                    "Frankenstein effect detected: unit tests pass but integration tests fail. "
                    "Subsystems work individually but fail when composed."
                ),
                evidence=integration_result.raw_output[:500],
            ))

        # Check for tests that pass in isolation but fail in full suite
        if unit_result.tests and integration_result.tests:
            unit_names = {t.name for t in unit_result.tests if t.passed}
            for test in integration_result.tests:
                if test.name in unit_names and not test.passed:
                    issues.append(CompositionIssue(
                        subsystems=subsystems or ["unknown"],
                        severity="warning",
                        description=f"Test '{test.name}' passes in isolation but fails in integration",
                        evidence=test.message,
                    ))

        success = not any(i.severity == "critical" for i in issues)

        return CompositionResult(
            success=success,
            issues=issues,
            build_ok=build_result.success,
            unit_tests_ok=unit_result.success,
            integration_tests_ok=integration_result.success,
            summary=f"{len(issues)} composition issues found" if issues else "No composition issues",
        )
