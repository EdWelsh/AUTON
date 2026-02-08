# AUTON Product Overview

## Project Purpose
AUTON is an autonomous agent orchestration system that builds SLM-driven operating system kernels from scratch. The system uses LLM agents to collaboratively write, review, test, and integrate custom kernels with embedded Small Language Models (SLMs) at their core.

## Core Value Proposition
- **Autonomous Development**: Agents write the kernel code - humans don't
- **SLM-Driven OS**: The kernel embeds an SLM as its central intelligence for hardware discovery, driver configuration, OS installation, and system administration
- **Multi-Architecture Support**: Supports x86_64, AArch64, and RISC-V 64 through Hardware Abstraction Layer (HAL)
- **VibeTensor Methodology**: Inspired by NVIDIA's approach where LLM agents generated ~195K lines of system software without human code review

## Key Features

### Agent Orchestration
- **8 Specialized Agent Types**: Manager, Architect, Developer (4x parallel), Reviewer, Tester, Integrator
- **Git-Based Collaboration**: Agents communicate through branches and structured diffs
- **Validation-Driven**: Agents are black boxes - validation only through builds and tests
- **Composition Detection**: Detects "Frankenstein effect" where locally correct subsystems fail when combined

### SLM Integration
- **Pluggable SLM Architecture**: Rule-based engine for minimal hardware, neural backend for rich inference
- **Intent Classification System**: `HARDWARE_IDENTIFY`, `DRIVER_SELECT`, `INSTALL_CONFIGURE`, `APP_INSTALL`, `SYSTEM_MANAGE`, `TROUBLESHOOT`
- **Training Pipeline**: Autonomous SLM training, quantization (INT4/INT8), and export (GGUF/ONNX)
- **Kernel Integration**: SLM embedded directly into kernel for runtime intelligence

### Multi-Architecture Support
- **x86_64**: Multiboot2, NASM, ACPI, 16550A UART, VGA, PIT, PS/2
- **AArch64**: DTB/UEFI, GNU AS, Device Tree, PL011 UART, GICv2, ARM Timer  
- **RISC-V 64**: OpenSBI + DTB, GNU AS, Device Tree, ns16550 UART, PLIC, CLINT

### Kernel Subsystems
- **Boot & Memory**: Architecture-specific boot protocols, bitmap PMM, multi-level paging VMM, slab allocator
- **Scheduling & IPC**: Preemptive round-robin with priority classes, structured message passing, ring buffers
- **Device Framework**: PCI enumeration, firmware parsing, uniform driver interface, SLM-driven loading
- **Filesystem & Network**: VFS layer, initramfs, ext2, devfs, procfs, Ethernet, ARP, IPv4, TCP/UDP, DHCP, DNS, HTTP
- **Package Management**: tar+manifest format, dependency resolution, SLM-driven installation

## Target Users

### Primary Users
- **OS Researchers**: Exploring autonomous kernel development and SLM-driven operating systems
- **AI/ML Engineers**: Investigating LLM agent collaboration for complex system software
- **Embedded Developers**: Building intelligent embedded systems with SLM-driven hardware management

### Use Cases
- **Research Platform**: Study autonomous software development methodologies
- **Embedded Intelligence**: Create self-configuring embedded systems
- **Educational Tool**: Learn OS development through agent-generated code
- **Prototype Development**: Rapid kernel prototyping for specialized hardware

## Technology Stack
- **Python**: Agent orchestration framework
- **Rust**: Build tooling, diff validation, QEMU test runner
- **LiteLLM**: Multi-provider LLM abstraction (Anthropic, OpenAI, Ollama, Gemini, OpenRouter, Azure)
- **PyTorch/Transformers**: SLM training and inference
- **Git**: Agent collaboration and version control
- **QEMU**: Kernel testing and validation

## Development Philosophy
- **Agents as Black Boxes**: Validation through tools, not human review
- **Composition Over Perfection**: Focus on subsystem integration over individual component optimization  
- **SLM-First Design**: Every OS operation flows through the embedded SLM intelligence
- **Multi-Architecture by Design**: Portable kernel architecture from day one