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


# Boot subsystem tests — portable (all architectures)
BOOT_TESTS_COMMON = [
    AcceptanceTest(
        name="boot_kernel_main",
        subsystem="boot",
        description="kernel_main() is called and prints banner",
        expected_serial_patterns=[
            r"AUTON Kernel booting",
        ],
    ),
    AcceptanceTest(
        name="boot_interrupts",
        subsystem="boot",
        description="Interrupt/exception table is set up",
        expected_serial_patterns=[
            r"\[BOOT\] Interrupts initialized",
        ],
    ),
    AcceptanceTest(
        name="boot_hw_handoff",
        subsystem="boot",
        description="Hardware summary collected and passed to kernel_main",
        expected_serial_patterns=[
            r"\[BOOT\] Hardware summary: \d+ MB RAM",
        ],
    ),
]

# Boot tests — architecture-specific
BOOT_TESTS_X86_64 = [
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
]

BOOT_TESTS_AARCH64 = [
    AcceptanceTest(
        name="boot_dtb_valid",
        subsystem="boot",
        description="Device Tree Blob parsed successfully",
        expected_serial_patterns=[
            r"\[BOOT\] DTB parsed",
        ],
    ),
    AcceptanceTest(
        name="boot_el1_entry",
        subsystem="boot",
        description="CPU entered EL1 from EL2",
        expected_serial_patterns=[
            r"\[BOOT\] Running at EL1",
        ],
    ),
]

BOOT_TESTS_RISCV64 = [
    AcceptanceTest(
        name="boot_dtb_valid",
        subsystem="boot",
        description="Device Tree Blob parsed successfully",
        expected_serial_patterns=[
            r"\[BOOT\] DTB parsed",
        ],
    ),
    AcceptanceTest(
        name="boot_smode_entry",
        subsystem="boot",
        description="CPU entered S-mode via OpenSBI",
        expected_serial_patterns=[
            r"\[BOOT\] Running in S-mode",
        ],
    ),
]

# Combined boot tests (backward compat)
BOOT_TESTS = BOOT_TESTS_COMMON + BOOT_TESTS_X86_64

# Memory management tests
MM_TESTS = [
    AcceptanceTest(
        name="mm_pmm_init",
        subsystem="mm",
        description="PMM initializes from boot memory map",
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
        name="mm_slm_pool",
        subsystem="mm",
        description="SLM memory pool allocated and accessible",
        expected_serial_patterns=[
            r"\[MM\] SLM pool: \d+ KB allocated",
        ],
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
        description="SLM priority class runs before USER tasks",
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
        description="Structured message send and receive",
        expected_serial_patterns=[
            r"\[TEST\] ipc_send_receive: PASS",
        ],
        requires_subsystems=["boot", "mm", "sched"],
    ),
    AcceptanceTest(
        name="ipc_slm_channel",
        subsystem="ipc",
        description="SLM command channel request/response works",
        expected_serial_patterns=[
            r"\[TEST\] ipc_slm_channel: PASS",
        ],
        requires_subsystems=["boot", "mm", "sched"],
    ),
]

# Device framework tests
DEV_TESTS = [
    AcceptanceTest(
        name="dev_pci_scan",
        subsystem="dev",
        description="PCI bus enumeration finds at least one device",
        expected_serial_patterns=[
            r"\[DEV\] PCI scan: \d+ devices found",
        ],
        requires_subsystems=["boot", "mm"],
    ),
    AcceptanceTest(
        name="dev_driver_register",
        subsystem="dev",
        description="Driver registration and probe callback works",
        expected_serial_patterns=[
            r"\[TEST\] dev_driver_register: PASS",
        ],
        requires_subsystems=["boot", "mm"],
    ),
]

# SLM runtime tests
SLM_TESTS = [
    AcceptanceTest(
        name="slm_rule_engine_init",
        subsystem="slm",
        description="Rule-based SLM backend initializes",
        expected_serial_patterns=[
            r"\[SLM\] Rule engine initialized",
        ],
        requires_subsystems=["boot", "mm"],
    ),
    AcceptanceTest(
        name="slm_intent_classify",
        subsystem="slm",
        description="SLM classifies a hardware identification intent",
        expected_serial_patterns=[
            r"\[TEST\] slm_intent_classify: PASS",
        ],
        requires_subsystems=["boot", "mm"],
    ),
    AcceptanceTest(
        name="slm_driver_select",
        subsystem="slm",
        description="SLM selects correct driver for a known PCI device",
        expected_serial_patterns=[
            r"\[TEST\] slm_driver_select: PASS",
        ],
        requires_subsystems=["boot", "mm", "dev"],
    ),
]

# Driver tests — portable
DRIVER_TESTS_COMMON = [
    AcceptanceTest(
        name="driver_serial_output",
        subsystem="drivers",
        description="Serial console outputs text (this test is self-proving)",
        expected_serial_patterns=[
            r"\[DRV\] Serial .+ initialized",
        ],
        requires_subsystems=["boot"],
    ),
    AcceptanceTest(
        name="driver_timer_tick",
        subsystem="drivers",
        description="System timer generates interrupts",
        expected_serial_patterns=[
            r"\[TEST\] timer_tick: PASS",
        ],
        requires_subsystems=["boot", "mm"],
    ),
]

# Driver tests — architecture-specific
DRIVER_TESTS_X86_64 = [
    AcceptanceTest(
        name="driver_vga_text",
        subsystem="drivers",
        description="VGA text mode driver displays output",
        expected_serial_patterns=[
            r"\[DRV\] VGA text initialized",
        ],
        requires_subsystems=["boot"],
    ),
]

DRIVER_TESTS_AARCH64 = [
    AcceptanceTest(
        name="driver_pl011",
        subsystem="drivers",
        description="PL011 UART driver initialized",
        expected_serial_patterns=[
            r"\[DRV\] PL011 initialized",
        ],
        requires_subsystems=["boot"],
    ),
]

DRIVER_TESTS_RISCV64 = [
    AcceptanceTest(
        name="driver_ns16550",
        subsystem="drivers",
        description="ns16550 UART driver initialized",
        expected_serial_patterns=[
            r"\[DRV\] ns16550 initialized",
        ],
        requires_subsystems=["boot"],
    ),
]

# Combined (backward compat)
DRIVER_TESTS = DRIVER_TESTS_COMMON + DRIVER_TESTS_X86_64

# Filesystem tests
FS_TESTS = [
    AcceptanceTest(
        name="fs_vfs_mount",
        subsystem="fs",
        description="VFS mounts initramfs at /",
        expected_serial_patterns=[
            r"\[FS\] Mounted initramfs at /",
        ],
        requires_subsystems=["boot", "mm"],
    ),
    AcceptanceTest(
        name="fs_read_write",
        subsystem="fs",
        description="Create, write, read, unlink a file in initramfs",
        expected_serial_patterns=[
            r"\[TEST\] fs_read_write: PASS",
        ],
        requires_subsystems=["boot", "mm"],
    ),
    AcceptanceTest(
        name="fs_devfs",
        subsystem="fs",
        description="devfs populates /dev with device nodes",
        expected_serial_patterns=[
            r"\[FS\] devfs mounted at /dev",
        ],
        requires_subsystems=["boot", "mm", "dev"],
    ),
]

# Network tests
NET_TESTS = [
    AcceptanceTest(
        name="net_stack_init",
        subsystem="net",
        description="Network stack initializes",
        expected_serial_patterns=[
            r"\[NET\] Stack initialized",
        ],
        requires_subsystems=["boot", "mm", "drivers"],
    ),
    AcceptanceTest(
        name="net_dhcp",
        subsystem="net",
        description="DHCP client obtains an IP address",
        expected_serial_patterns=[
            r"\[NET\] DHCP: obtained \d+\.\d+\.\d+\.\d+",
        ],
        timeout_secs=30,
        requires_subsystems=["boot", "mm", "drivers", "dev"],
    ),
]

# Integration tests
INTEGRATION_TESTS = [
    AcceptanceTest(
        name="full_boot_to_slm",
        subsystem="integration",
        description="Full system: boot → init subsystems → SLM ready",
        expected_serial_patterns=[
            r"AUTON Kernel booting",
            r"\[MM\] PMM initialized",
            r"\[SCHED\] Scheduler initialized",
            r"\[SLM\] .+ engine initialized",
            r"\[SLM\] Ready",
        ],
        timeout_secs=60,
        requires_subsystems=["boot", "mm", "sched", "ipc", "dev", "slm", "drivers"],
    ),
    AcceptanceTest(
        name="slm_hw_discovery",
        subsystem="integration",
        description="SLM discovers hardware and loads at least one driver",
        expected_serial_patterns=[
            r"\[SLM\] Hardware scan complete: \d+ devices",
            r"\[SLM\] Loaded driver:",
        ],
        timeout_secs=60,
        requires_subsystems=["boot", "mm", "sched", "dev", "slm", "drivers"],
    ),
    AcceptanceTest(
        name="slm_full_setup",
        subsystem="integration",
        description="SLM performs full setup: hw detect → drivers → filesystem → ready",
        expected_serial_patterns=[
            r"\[SLM\] Hardware scan complete",
            r"\[SLM\] Loaded driver:",
            r"\[FS\] Mounted",
            r"\[SLM\] System ready",
        ],
        timeout_secs=120,
        requires_subsystems=["boot", "mm", "sched", "ipc", "dev", "slm", "drivers", "fs"],
    ),
]

# All tests grouped (default x86_64)
ALL_TESTS = {
    "boot": BOOT_TESTS,
    "mm": MM_TESTS,
    "sched": SCHED_TESTS,
    "ipc": IPC_TESTS,
    "dev": DEV_TESTS,
    "slm": SLM_TESTS,
    "drivers": DRIVER_TESTS,
    "fs": FS_TESTS,
    "net": NET_TESTS,
    "integration": INTEGRATION_TESTS,
}


# --- Architecture-aware test accessors ---

_ARCH_BOOT_TESTS = {
    "x86_64": BOOT_TESTS_X86_64,
    "aarch64": BOOT_TESTS_AARCH64,
    "riscv64": BOOT_TESTS_RISCV64,
}

_ARCH_DRIVER_TESTS = {
    "x86_64": DRIVER_TESTS_X86_64,
    "aarch64": DRIVER_TESTS_AARCH64,
    "riscv64": DRIVER_TESTS_RISCV64,
}


def get_boot_tests(arch: str) -> list[AcceptanceTest]:
    """Get boot tests for a specific architecture."""
    arch_tests = _ARCH_BOOT_TESTS.get(arch, [])
    return BOOT_TESTS_COMMON + arch_tests


def get_driver_tests(arch: str) -> list[AcceptanceTest]:
    """Get driver tests for a specific architecture."""
    arch_tests = _ARCH_DRIVER_TESTS.get(arch, [])
    return DRIVER_TESTS_COMMON + arch_tests


def get_all_tests(arch: str) -> dict[str, list[AcceptanceTest]]:
    """Get all tests for a specific architecture.

    Returns a dict keyed by subsystem name with per-arch test lists.
    """
    return {
        "boot": get_boot_tests(arch),
        "mm": MM_TESTS,
        "sched": SCHED_TESTS,
        "ipc": IPC_TESTS,
        "dev": DEV_TESTS,
        "slm": SLM_TESTS,
        "drivers": get_driver_tests(arch),
        "fs": FS_TESTS,
        "net": NET_TESTS,
        "integration": INTEGRATION_TESTS,
    }
