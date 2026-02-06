"""Acceptance test definitions for the AUTON kernel.

These tests define what the agents must achieve. The orchestrator runs
these after kernel code is generated to verify correctness.

Tests work by:
1. Building the kernel
2. Booting it in QEMU with serial output capture
3. Parsing serial output for [TEST], [BOOT], and diagnostic markers
"""

import re
from dataclasses import dataclass


@dataclass
class AcceptanceTest:
    """Definition of an acceptance test."""

    name: str
    subsystem: str
    description: str
    expected_serial_patterns: list[str]
    timeout_secs: int = 30
    requires_subsystems: list[str] | None = None


# Boot subsystem tests
BOOT_TESTS = [
    AcceptanceTest(
        name="boot_multiboot2",
        subsystem="boot",
        description="Kernel loads via Multiboot2 and validates magic number",
        expected_serial_patterns=[
            r"\[BOOT\] Multiboot2 magic valid",
        ],
    ),
    AcceptanceTest(
        name="boot_long_mode",
        subsystem="boot",
        description="CPU transitions to 64-bit long mode",
        expected_serial_patterns=[
            r"\[BOOT\] Long mode enabled",
            r"\[BOOT\] 64-bit GDT loaded",
        ],
    ),
    AcceptanceTest(
        name="boot_kernel_main",
        subsystem="boot",
        description="kernel_main() is called and prints banner",
        expected_serial_patterns=[
            r"AUTON Kernel booting",
        ],
    ),
    AcceptanceTest(
        name="boot_idt",
        subsystem="boot",
        description="IDT is loaded with exception handlers",
        expected_serial_patterns=[
            r"\[BOOT\] IDT loaded",
        ],
    ),
]

# Memory management tests
MM_TESTS = [
    AcceptanceTest(
        name="mm_pmm_init",
        subsystem="mm",
        description="PMM initializes from Multiboot2 memory map",
        expected_serial_patterns=[
            r"\[MM\] PMM initialized: \d+ pages free",
        ],
        requires_subsystems=["boot"],
    ),
    AcceptanceTest(
        name="mm_pmm_alloc_free",
        subsystem="mm",
        description="Page allocation and free round-trip",
        expected_serial_patterns=[
            r"\[TEST\] pmm_alloc_free: PASS",
        ],
        requires_subsystems=["boot"],
    ),
    AcceptanceTest(
        name="mm_vmm_map",
        subsystem="mm",
        description="Virtual memory mapping works",
        expected_serial_patterns=[
            r"\[TEST\] vmm_map_page: PASS",
        ],
        requires_subsystems=["boot"],
    ),
    AcceptanceTest(
        name="mm_slab_alloc",
        subsystem="mm",
        description="Slab allocator handles various sizes",
        expected_serial_patterns=[
            r"\[TEST\] slab_alloc_\d+: PASS",
        ],
        requires_subsystems=["boot"],
    ),
    AcceptanceTest(
        name="mm_stress",
        subsystem="mm",
        description="10000 alloc/free cycles without leaks",
        expected_serial_patterns=[
            r"\[TEST\] mm_stress_10k: PASS",
        ],
        timeout_secs=60,
        requires_subsystems=["boot"],
    ),
]

# Scheduler tests
SCHED_TESTS = [
    AcceptanceTest(
        name="sched_create_process",
        subsystem="sched",
        description="Process creation and listing",
        expected_serial_patterns=[
            r"\[TEST\] sched_create: PASS",
        ],
        requires_subsystems=["boot", "mm"],
    ),
    AcceptanceTest(
        name="sched_context_switch",
        subsystem="sched",
        description="Context switch between two processes",
        expected_serial_patterns=[
            r"\[TEST\] context_switch: PASS",
        ],
        requires_subsystems=["boot", "mm"],
    ),
    AcceptanceTest(
        name="sched_priority",
        subsystem="sched",
        description="Priority classes are respected",
        expected_serial_patterns=[
            r"\[TEST\] sched_priority: PASS",
        ],
        requires_subsystems=["boot", "mm"],
    ),
]

# IPC tests
IPC_TESTS = [
    AcceptanceTest(
        name="ipc_send_receive",
        subsystem="ipc",
        description="Message send and receive between two agents",
        expected_serial_patterns=[
            r"\[TEST\] ipc_send_receive: PASS",
        ],
        requires_subsystems=["boot", "mm", "sched"],
    ),
    AcceptanceTest(
        name="ipc_utf8",
        subsystem="ipc",
        description="UTF-8 message content preserved correctly",
        expected_serial_patterns=[
            r"\[TEST\] ipc_utf8: PASS",
        ],
        requires_subsystems=["boot", "mm", "sched"],
    ),
]

# NL Syscall tests
NL_SYSCALL_TESTS = [
    AcceptanceTest(
        name="nl_allocate",
        subsystem="nl_syscall",
        description="'allocate 4KB of memory' works",
        expected_serial_patterns=[
            r"\[TEST\] nl_allocate: PASS",
        ],
        requires_subsystems=["boot", "mm", "llm_runtime"],
    ),
    AcceptanceTest(
        name="nl_send_message",
        subsystem="nl_syscall",
        description="'send message to agent 2: hello' works",
        expected_serial_patterns=[
            r"\[TEST\] nl_send_message: PASS",
        ],
        requires_subsystems=["boot", "mm", "sched", "ipc", "llm_runtime"],
    ),
    AcceptanceTest(
        name="nl_list_processes",
        subsystem="nl_syscall",
        description="'list running processes' works",
        expected_serial_patterns=[
            r"\[TEST\] nl_list_processes: PASS",
        ],
        requires_subsystems=["boot", "mm", "sched", "llm_runtime"],
    ),
]

# Integration tests
INTEGRATION_TESTS = [
    AcceptanceTest(
        name="full_boot_to_nl",
        subsystem="integration",
        description="Full system: boot → init subsystems → process NL command",
        expected_serial_patterns=[
            r"AUTON Kernel booting",
            r"\[MM\] PMM initialized",
            r"\[SCHED\] Scheduler initialized",
            r"\[NL\] NL syscall interface ready",
            r"\[TEST\] full_integration: PASS",
        ],
        timeout_secs=60,
        requires_subsystems=["boot", "mm", "sched", "ipc", "nl_syscall", "llm_runtime", "drivers"],
    ),
]

# All tests grouped
ALL_TESTS = {
    "boot": BOOT_TESTS,
    "mm": MM_TESTS,
    "sched": SCHED_TESTS,
    "ipc": IPC_TESTS,
    "nl_syscall": NL_SYSCALL_TESTS,
    "integration": INTEGRATION_TESTS,
}
