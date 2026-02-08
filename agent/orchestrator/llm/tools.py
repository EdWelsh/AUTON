"""Tool definitions for LLM tool-use. These are the capabilities agents can invoke.

Uses OpenAI/LiteLLM format: {type: "function", function: {name, description, parameters}}.
"""

from __future__ import annotations

TOOL_READ_FILE = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read the contents of a file from the kernel workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from workspace root (e.g. 'kernel/mm/page_alloc.c')",
                },
            },
            "required": ["path"],
        },
    },
}

TOOL_WRITE_FILE = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Write content to a file in the kernel workspace. Creates parent directories if needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from workspace root",
                },
                "content": {
                    "type": "string",
                    "description": "The full content to write to the file",
                },
            },
            "required": ["path", "content"],
        },
    },
}

TOOL_SEARCH_CODE = {
    "type": "function",
    "function": {
        "name": "search_code",
        "description": "Search for a pattern in the kernel workspace using regex.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "glob": {
                    "type": "string",
                    "description": "File glob pattern to filter (e.g. '*.c', '*.h'). Default: all files.",
                },
            },
            "required": ["pattern"],
        },
    },
}

TOOL_LIST_FILES = {
    "type": "function",
    "function": {
        "name": "list_files",
        "description": "List files in a directory of the kernel workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative directory path from workspace root. Default: root.",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "List files recursively. Default: false.",
                },
            },
            "required": [],
        },
    },
}

TOOL_BUILD_KERNEL = {
    "type": "function",
    "function": {
        "name": "build_kernel",
        "description": "Compile the kernel code. Returns build output including any errors.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Build target: 'all', 'boot', 'kernel', 'clean'. Default: 'all'.",
                },
            },
            "required": [],
        },
    },
}

TOOL_RUN_TEST = {
    "type": "function",
    "function": {
        "name": "run_test",
        "description": "Run a specific test or all tests. Boots the kernel in QEMU for integration tests.",
        "parameters": {
            "type": "object",
            "properties": {
                "test_name": {
                    "type": "string",
                    "description": "Name of the test to run, or 'all' for all tests.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds. Default: 60.",
                },
            },
            "required": ["test_name"],
        },
    },
}

TOOL_GIT_COMMIT = {
    "type": "function",
    "function": {
        "name": "git_commit",
        "description": "Stage and commit changes in the kernel workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Commit message describing the change.",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file paths to stage. If empty, stages all changes.",
                },
            },
            "required": ["message"],
        },
    },
}

TOOL_GIT_DIFF = {
    "type": "function",
    "function": {
        "name": "git_diff",
        "description": "Show the current uncommitted changes or diff between branches.",
        "parameters": {
            "type": "object",
            "properties": {
                "branch": {
                    "type": "string",
                    "description": "Compare against this branch. Default: show working tree changes.",
                },
            },
            "required": [],
        },
    },
}

TOOL_READ_SPEC = {
    "type": "function",
    "function": {
        "name": "read_spec",
        "description": "Read a kernel subsystem specification document.",
        "parameters": {
            "type": "object",
            "properties": {
                "subsystem": {
                    "type": "string",
                    "description": "Subsystem name: 'architecture', 'boot', 'mm', 'sched', 'ipc', 'dev', 'slm', 'drivers', 'fs', 'net', 'pkg', 'sys', 'hal', 'arch/x86_64', 'arch/aarch64', 'arch/riscv64'.",
                },
            },
            "required": ["subsystem"],
        },
    },
}

TOOL_SHELL = {
    "type": "function",
    "function": {
        "name": "shell",
        "description": "Execute a shell command in the kernel workspace. Use for build tools, QEMU, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds. Default: 120.",
                },
            },
            "required": ["command"],
        },
    },
}

# SLM-specific tools
TOOL_TRAIN_MODEL = {
    "type": "function",
    "function": {
        "name": "train_model",
        "description": "Train an SLM model using PyTorch. Runs SLM/scripts/train.py with config.",
        "parameters": {
            "type": "object",
            "properties": {
                "config_path": {
                    "type": "string",
                    "description": "Path to model config YAML (e.g. 'SLM/configs/tiny_10M.yaml')",
                },
                "dataset_path": {
                    "type": "string",
                    "description": "Path to processed dataset",
                },
                "max_steps": {
                    "type": "integer",
                    "description": "Maximum training steps. Default: 10000.",
                },
            },
            "required": ["config_path", "dataset_path"],
        },
    },
}

TOOL_EVALUATE_MODEL = {
    "type": "function",
    "function": {
        "name": "evaluate_model",
        "description": "Evaluate a trained model checkpoint. Computes perplexity and benchmarks.",
        "parameters": {
            "type": "object",
            "properties": {
                "checkpoint_path": {
                    "type": "string",
                    "description": "Path to model checkpoint",
                },
                "test_dataset": {
                    "type": "string",
                    "description": "Path to test dataset",
                },
            },
            "required": ["checkpoint_path", "test_dataset"],
        },
    },
}

TOOL_QUANTIZE_MODEL = {
    "type": "function",
    "function": {
        "name": "quantize_model",
        "description": "Quantize model to INT4/INT8 using GPTQ or AWQ.",
        "parameters": {
            "type": "object",
            "properties": {
                "checkpoint_path": {
                    "type": "string",
                    "description": "Path to model checkpoint",
                },
                "bits": {
                    "type": "integer",
                    "description": "Quantization bits: 4 or 8. Default: 4.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Output path for quantized model",
                },
            },
            "required": ["checkpoint_path", "output_path"],
        },
    },
}

TOOL_EXPORT_GGUF = {
    "type": "function",
    "function": {
        "name": "export_gguf",
        "description": "Export model to GGUF format for kernel integration.",
        "parameters": {
            "type": "object",
            "properties": {
                "model_path": {
                    "type": "string",
                    "description": "Path to quantized model",
                },
                "output_path": {
                    "type": "string",
                    "description": "Output GGUF file path",
                },
            },
            "required": ["model_path", "output_path"],
        },
    },
}

# Tool sets by agent role
MANAGER_TOOLS = [TOOL_READ_SPEC, TOOL_LIST_FILES, TOOL_READ_FILE, TOOL_SEARCH_CODE]

ARCHITECT_TOOLS = [
    TOOL_READ_SPEC,
    TOOL_READ_FILE,
    TOOL_WRITE_FILE,
    TOOL_LIST_FILES,
    TOOL_SEARCH_CODE,
]

DEVELOPER_TOOLS = [
    TOOL_READ_SPEC,
    TOOL_READ_FILE,
    TOOL_WRITE_FILE,
    TOOL_LIST_FILES,
    TOOL_SEARCH_CODE,
    TOOL_BUILD_KERNEL,
    TOOL_RUN_TEST,
    TOOL_GIT_COMMIT,
    TOOL_GIT_DIFF,
    TOOL_SHELL,
]

REVIEWER_TOOLS = [
    TOOL_READ_FILE,
    TOOL_LIST_FILES,
    TOOL_SEARCH_CODE,
    TOOL_GIT_DIFF,
    TOOL_READ_SPEC,
]

TESTER_TOOLS = [
    TOOL_READ_FILE,
    TOOL_WRITE_FILE,
    TOOL_LIST_FILES,
    TOOL_SEARCH_CODE,
    TOOL_BUILD_KERNEL,
    TOOL_RUN_TEST,
    TOOL_GIT_COMMIT,
    TOOL_GIT_DIFF,
    TOOL_SHELL,
]

INTEGRATOR_TOOLS = [
    TOOL_READ_FILE,
    TOOL_WRITE_FILE,
    TOOL_LIST_FILES,
    TOOL_SEARCH_CODE,
    TOOL_BUILD_KERNEL,
    TOOL_RUN_TEST,
    TOOL_GIT_COMMIT,
    TOOL_GIT_DIFF,
    TOOL_SHELL,
]

# SLM agent tool sets
TRAINING_TOOLS = [
    TOOL_READ_FILE,
    TOOL_WRITE_FILE,
    TOOL_LIST_FILES,
    TOOL_TRAIN_MODEL,
    TOOL_EVALUATE_MODEL,
    TOOL_QUANTIZE_MODEL,
    TOOL_EXPORT_GGUF,
    TOOL_SHELL,
]
