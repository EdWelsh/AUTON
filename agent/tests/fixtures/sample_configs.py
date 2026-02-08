"""Sample configurations for testing."""


VALID_CONFIG = {
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
    "workspace": {
        "path": "../kernels/x86_64",
    },
}


AARCH64_CONFIG = {**VALID_CONFIG, "kernel": {"arch": "aarch64"}}
RISCV64_CONFIG = {**VALID_CONFIG, "kernel": {"arch": "riscv64"}}
SLM_WORKFLOW_CONFIG = {**VALID_CONFIG, "workflow": {"mode": "slm_training"}}
DUAL_WORKFLOW_CONFIG = {**VALID_CONFIG, "workflow": {"mode": "dual"}}
