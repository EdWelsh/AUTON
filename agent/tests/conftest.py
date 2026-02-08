"""Pytest configuration and shared fixtures."""

import pytest


@pytest.fixture
def sample_config():
    """Sample AUTON configuration."""
    return {
        "llm": {
            "model": "anthropic/claude-opus-4-6",
            "max_tokens": 16384,
            "temperature": 0.0,
        },
        "agents": {
            "developer_count": 4,
            "reviewer_count": 1,
        },
        "kernel": {
            "arch": "x86_64",
        },
        "validation": {
            "build_timeout": 120,
            "test_timeout": 60,
            "composition_checks": True,
        },
        "workflow": {
            "mode": "kernel_build",
        },
    }


@pytest.fixture
def sample_task():
    """Sample task definition."""
    return {
        "task_id": "boot-001",
        "title": "Implement boot loader",
        "subsystem": "boot",
        "description": "Create Multiboot2 boot loader",
        "dependencies": [],
        "acceptance_criteria": ["Kernel boots", "Serial output works"],
    }
