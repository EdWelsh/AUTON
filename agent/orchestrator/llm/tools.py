"""Tool definitions for Claude tool-use. These are the capabilities agents can invoke."""

from __future__ import annotations

TOOL_READ_FILE = {
    "name": "read_file",
    "description": "Read the contents of a file from the kernel workspace.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path from workspace root (e.g. 'kernel/mm/page_alloc.c')",
            },
        },
        "required": ["path"],
    },
}

TOOL_WRITE_FILE = {
    "name": "write_file",
    "description": "Write content to a file in the kernel workspace. Creates parent directories if needed.",
    "input_schema": {
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
}

TOOL_SEARCH_CODE = {
    "name": "search_code",
    "description": "Search for a pattern in the kernel workspace using regex.",
    "input_schema": {
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
}

TOOL_LIST_FILES = {
    "name": "list_files",
    "description": "List files in a directory of the kernel workspace.",
    "input_schema": {
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
}

TOOL_BUILD_KERNEL = {
    "name": "build_kernel",
    "description": "Compile the kernel code. Returns build output including any errors.",
    "input_schema": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Build target: 'all', 'boot', 'kernel', 'clean'. Default: 'all'.",
            },
        },
        "required": [],
    },
}

TOOL_RUN_TEST = {
    "name": "run_test",
    "description": "Run a specific test or all tests. Boots the kernel in QEMU for integration tests.",
    "input_schema": {
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
}

TOOL_GIT_COMMIT = {
    "name": "git_commit",
    "description": "Stage and commit changes in the kernel workspace.",
    "input_schema": {
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
}

TOOL_GIT_DIFF = {
    "name": "git_diff",
    "description": "Show the current uncommitted changes or diff between branches.",
    "input_schema": {
        "type": "object",
        "properties": {
            "branch": {
                "type": "string",
                "description": "Compare against this branch. Default: show working tree changes.",
            },
        },
        "required": [],
    },
}

TOOL_READ_SPEC = {
    "name": "read_spec",
    "description": "Read a kernel subsystem specification document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subsystem": {
                "type": "string",
                "description": "Subsystem name: 'architecture', 'boot', 'mm', 'sched', 'ipc', 'nl_syscall', 'hypervisor', 'drivers', 'llm_runtime'.",
            },
        },
        "required": ["subsystem"],
    },
}

TOOL_SHELL = {
    "name": "shell",
    "description": "Execute a shell command in the kernel workspace. Use for build tools, QEMU, etc.",
    "input_schema": {
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
