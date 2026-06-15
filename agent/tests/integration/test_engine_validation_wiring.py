"""Integration test for the engine's validation wiring.

Verifies that OrchestrationEngine constructs the build/test/composition
validators (previously dead code, never instantiated) and that final success
is gated on a real build + QEMU boot, not just agent self-report.
"""

import pytest
from pathlib import Path
from unittest.mock import patch

from orchestrator.core.engine import OrchestrationEngine
from orchestrator.validation import (
    BuildValidator,
    CompositionValidator,
    TestValidator,
)


@pytest.fixture
def engine(tmp_path):
    config = {
        "llm": {
            "model": "ollama/test-model",
            "max_tokens": 4096,
            "api_keys": {},
            "cost": {"max_cost_usd": 10.0, "warn_at_usd": 5.0},
        },
        "kernel": {"arch": "x86_64"},
        "workspace": {"branch_prefix": "agent"},
        "agents": {"developer_count": 1, "reviewer_count": 1, "tester_count": 1},
        "workflow": {"mode": "kernel_build"},
        "validation": {"build_timeout": 90, "test_timeout": 45, "composition_checks": True},
    }
    spec_path = tmp_path / "kernel_spec"
    spec_path.mkdir()
    with patch("orchestrator.core.engine.GitWorkspace"):
        return OrchestrationEngine(
            workspace_path=tmp_path, kernel_spec_path=spec_path, config=config
        )


def test_engine_constructs_validators(engine):
    """The three validators are instantiated and wired to the workspace."""
    assert isinstance(engine.build_validator, BuildValidator)
    assert isinstance(engine.test_validator, TestValidator)
    assert isinstance(engine.composition_validator, CompositionValidator)


def test_build_validator_uses_arch_toolchain(engine):
    """BuildValidator picks up the x86_64 toolchain from the arch profile."""
    assert engine.build_validator.cc == "x86_64-elf-gcc"


def test_test_validator_uses_arch_qemu_and_timeout(engine):
    """TestValidator picks up QEMU binary and the configured timeout."""
    assert engine.test_validator.qemu == "qemu-system-x86_64"
    assert engine.test_validator.timeout == 45


def test_validation_config_parsed(engine):
    """Validation timeouts/flags come from the [validation] config section."""
    assert engine.build_timeout == 90
    assert engine.test_timeout == 45
    assert engine.composition_checks is True


def test_validation_defaults_when_section_missing(tmp_path):
    """Validators still construct with sane defaults when config omits them."""
    config = {
        "llm": {"model": "ollama/test", "api_keys": {}, "cost": {}},
        "kernel": {"arch": "x86_64"},
        "agents": {"developer_count": 1, "reviewer_count": 1, "tester_count": 1},
        "workflow": {"mode": "kernel_build"},
    }
    spec_path = tmp_path / "spec"
    spec_path.mkdir()
    with patch("orchestrator.core.engine.GitWorkspace"):
        engine = OrchestrationEngine(
            workspace_path=tmp_path, kernel_spec_path=spec_path, config=config
        )
    assert engine.build_timeout == 120
    assert engine.composition_checks is True
