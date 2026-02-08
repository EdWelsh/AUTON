"""Unit tests for orchestrator.validation.composition_validator."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.validation.composition_validator import (
    CompositionIssue,
    CompositionResult,
    CompositionValidator,
)
from orchestrator.validation.build_validator import BuildValidator
from orchestrator.validation.test_validator import TestValidator


# ---------------------------------------------------------------------------
# CompositionIssue dataclass
# ---------------------------------------------------------------------------

class TestCompositionIssue:
    """Tests for the CompositionIssue dataclass."""

    def test_creation_minimal(self):
        issue = CompositionIssue(
            subsystems=["mm", "scheduler"],
            severity="critical",
            description="Deadlock between memory manager and scheduler",
        )
        assert issue.subsystems == ["mm", "scheduler"]
        assert issue.severity == "critical"
        assert issue.description == "Deadlock between memory manager and scheduler"
        assert issue.evidence == ""

    def test_creation_with_evidence(self):
        issue = CompositionIssue(
            subsystems=["boot"],
            severity="warning",
            description="Boot sequence slower than expected",
            evidence="Boot took 5.2s, expected < 2s",
        )
        assert issue.evidence == "Boot took 5.2s, expected < 2s"

    def test_severity_critical(self):
        issue = CompositionIssue(
            subsystems=["vfs", "block"],
            severity="critical",
            description="File system corruption under concurrent access",
        )
        assert issue.severity == "critical"

    def test_severity_warning(self):
        issue = CompositionIssue(
            subsystems=["net"],
            severity="warning",
            description="Network throughput degraded",
        )
        assert issue.severity == "warning"

    def test_severity_info(self):
        issue = CompositionIssue(
            subsystems=["serial"],
            severity="info",
            description="Serial output buffering enabled",
        )
        assert issue.severity == "info"

    def test_multiple_subsystems(self):
        issue = CompositionIssue(
            subsystems=["mm", "scheduler", "ipc"],
            severity="critical",
            description="Three-way interaction failure",
        )
        assert len(issue.subsystems) == 3
        assert "ipc" in issue.subsystems

    def test_single_subsystem(self):
        issue = CompositionIssue(
            subsystems=["boot"],
            severity="warning",
            description="Boot self-check warning",
        )
        assert len(issue.subsystems) == 1


# ---------------------------------------------------------------------------
# CompositionResult dataclass
# ---------------------------------------------------------------------------

class TestCompositionResult:
    """Tests for the CompositionResult dataclass."""

    def test_creation_with_defaults(self):
        cr = CompositionResult(success=True)
        assert cr.success is True
        assert cr.issues == []
        assert cr.build_ok is False
        assert cr.unit_tests_ok is False
        assert cr.integration_tests_ok is False
        assert cr.summary == ""

    def test_success_with_no_critical_issues(self):
        cr = CompositionResult(
            success=True,
            issues=[
                CompositionIssue(
                    subsystems=["mm"],
                    severity="warning",
                    description="Minor issue",
                ),
            ],
            build_ok=True,
            unit_tests_ok=True,
            integration_tests_ok=True,
            summary="1 composition issues found",
        )
        assert cr.success is True
        assert len(cr.issues) == 1

    def test_failure_with_critical_issue(self):
        cr = CompositionResult(
            success=False,
            issues=[
                CompositionIssue(
                    subsystems=["mm", "scheduler"],
                    severity="critical",
                    description="Frankenstein effect detected",
                ),
            ],
            build_ok=True,
            unit_tests_ok=True,
            integration_tests_ok=False,
            summary="1 composition issues found",
        )
        assert cr.success is False
        assert cr.issues[0].severity == "critical"

    def test_issues_list_is_independent(self):
        r1 = CompositionResult(success=True)
        r2 = CompositionResult(success=True)
        r1.issues.append(
            CompositionIssue(subsystems=["x"], severity="info", description="test")
        )
        assert r2.issues == []

    def test_full_construction(self):
        issues = [
            CompositionIssue(
                subsystems=["a", "b"],
                severity="critical",
                description="desc1",
                evidence="ev1",
            ),
            CompositionIssue(
                subsystems=["c"],
                severity="warning",
                description="desc2",
            ),
        ]
        cr = CompositionResult(
            success=False,
            issues=issues,
            build_ok=True,
            unit_tests_ok=True,
            integration_tests_ok=False,
            summary="2 composition issues found",
        )
        assert cr.success is False
        assert len(cr.issues) == 2
        assert cr.build_ok is True
        assert cr.unit_tests_ok is True
        assert cr.integration_tests_ok is False
        assert "2 composition" in cr.summary

    def test_build_failure_result(self):
        cr = CompositionResult(
            success=False,
            build_ok=False,
            summary="Build failed: missing header",
        )
        assert cr.build_ok is False
        assert "Build failed" in cr.summary

    def test_empty_issues_means_no_problems(self):
        cr = CompositionResult(
            success=True,
            issues=[],
            build_ok=True,
            unit_tests_ok=True,
            integration_tests_ok=True,
            summary="No composition issues",
        )
        assert cr.success is True
        assert len(cr.issues) == 0
        assert cr.summary == "No composition issues"


# ---------------------------------------------------------------------------
# CompositionValidator.__init__
# ---------------------------------------------------------------------------

class TestCompositionValidatorInit:
    """Tests for CompositionValidator initialisation."""

    def test_creates_build_validator(self, tmp_path: Path):
        cv = CompositionValidator(workspace_path=tmp_path)
        assert isinstance(cv.build_validator, BuildValidator)
        assert cv.build_validator.workspace_path == tmp_path

    def test_creates_test_validator(self, tmp_path: Path):
        cv = CompositionValidator(workspace_path=tmp_path)
        assert isinstance(cv.test_validator, TestValidator)
        assert cv.test_validator.workspace_path == tmp_path

    def test_stores_workspace_path(self, tmp_path: Path):
        cv = CompositionValidator(workspace_path=tmp_path)
        assert cv.workspace_path == tmp_path

    def test_build_validator_has_default_toolchain(self, tmp_path: Path):
        cv = CompositionValidator(workspace_path=tmp_path)
        assert cv.build_validator.cc == "x86_64-elf-gcc"
        assert cv.build_validator.asm == "nasm"

    def test_test_validator_has_default_qemu(self, tmp_path: Path):
        cv = CompositionValidator(workspace_path=tmp_path)
        assert cv.test_validator.qemu == "qemu-system-x86_64"
        assert cv.test_validator.timeout == 60
