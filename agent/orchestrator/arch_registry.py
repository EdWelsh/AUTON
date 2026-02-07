"""Architecture registry — defines supported target architectures.

Each architecture has a complete profile specifying toolchain, QEMU config,
boot protocol, register set, and other arch-specific details. Adding a new
architecture requires only adding an entry to ARCH_PROFILES.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ArchProfile:
    """Complete profile for a target architecture."""

    name: str
    display_name: str

    # Toolchain
    cc: str
    asm: str
    ld: str
    asm_syntax: str  # "nasm" or "gas"
    asm_format: str  # e.g. "-f elf64" for NASM, "" for GAS
    cflags: list[str] = field(default_factory=list)

    # QEMU
    qemu: str = ""
    qemu_machine: str = ""
    qemu_cpu: str = ""
    qemu_extra: list[str] = field(default_factory=list)

    # Boot protocol
    boot_protocol: str = ""  # "multiboot2", "dtb", "sbi+dtb"
    firmware_type: str = ""  # "acpi", "device_tree", "both"

    # Assembly language name for prompts
    asm_language: str = ""

    # Register naming (for prompt context)
    register_set: str = ""
    page_table_format: str = ""

    # Spec file reference
    arch_spec_file: str = ""

    # Core drivers available for this architecture
    core_drivers: list[str] = field(default_factory=list)


ARCH_PROFILES: dict[str, ArchProfile] = {
    "x86_64": ArchProfile(
        name="x86_64",
        display_name="x86_64 (AMD64)",
        cc="x86_64-elf-gcc",
        asm="nasm",
        ld="x86_64-elf-ld",
        asm_syntax="nasm",
        asm_format="-f elf64",
        cflags=["-ffreestanding", "-mno-red-zone", "-fno-exceptions", "-mcmodel=kernel"],
        qemu="qemu-system-x86_64",
        qemu_machine="",
        qemu_cpu="",
        qemu_extra=[],
        boot_protocol="multiboot2",
        firmware_type="acpi",
        asm_language="NASM x86_64 Assembly",
        register_set="RAX-R15, RSP, RBP, RFLAGS, CR3",
        page_table_format="4-level (PML4 -> PDPT -> PD -> PT)",
        arch_spec_file="arch/x86_64.md",
        core_drivers=["serial_16550", "vga_text", "pit_8254", "ps2_keyboard"],
    ),
    "aarch64": ArchProfile(
        name="aarch64",
        display_name="AArch64 (ARM64)",
        cc="aarch64-elf-gcc",
        asm="aarch64-elf-as",
        ld="aarch64-elf-ld",
        asm_syntax="gas",
        asm_format="",
        cflags=["-ffreestanding", "-mgeneral-regs-only", "-fno-exceptions"],
        qemu="qemu-system-aarch64",
        qemu_machine="virt",
        qemu_cpu="cortex-a53",
        qemu_extra=["-nographic"],
        boot_protocol="dtb",
        firmware_type="device_tree",
        asm_language="AArch64 Assembly (GNU AS)",
        register_set="X0-X30, SP, LR(X30), FP(X29), TTBR0/TTBR1",
        page_table_format="4-level translation tables (4KB granule)",
        arch_spec_file="arch/aarch64.md",
        core_drivers=["pl011_uart", "gicv2", "arm_timer"],
    ),
    "riscv64": ArchProfile(
        name="riscv64",
        display_name="RISC-V 64-bit",
        cc="riscv64-elf-gcc",
        asm="riscv64-elf-as",
        ld="riscv64-elf-ld",
        asm_syntax="gas",
        asm_format="",
        cflags=["-ffreestanding", "-fno-exceptions", "-march=rv64gc", "-mabi=lp64d"],
        qemu="qemu-system-riscv64",
        qemu_machine="virt",
        qemu_cpu="",
        qemu_extra=["-bios", "default", "-nographic"],
        boot_protocol="sbi+dtb",
        firmware_type="device_tree",
        asm_language="RISC-V Assembly (GNU AS)",
        register_set="x0-x31 (a0-a7, s0-s11, t0-t6), satp CSR",
        page_table_format="Sv39 3-level paging",
        arch_spec_file="arch/riscv64.md",
        core_drivers=["ns16550_uart", "plic", "clint_timer"],
    ),
}


def get_arch_profile(arch: str) -> ArchProfile:
    """Get architecture profile by name. Raises KeyError if not found."""
    if arch not in ARCH_PROFILES:
        supported = ", ".join(sorted(ARCH_PROFILES.keys()))
        raise KeyError(f"Unsupported architecture '{arch}'. Supported: {supported}")
    return ARCH_PROFILES[arch]


def list_architectures() -> list[str]:
    """Return list of supported architecture names."""
    return sorted(ARCH_PROFILES.keys())
