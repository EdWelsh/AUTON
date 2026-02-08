# AUTON

**Autonomous agent orchestration system that builds an SLM-driven operating system kernel from scratch.**

AUTON uses LLM agents to collaboratively write, review, test, and integrate a custom kernel with an embedded **Small Language Model (SLM)** at its core. The SLM serves as the OS's central intelligence — handling hardware discovery, driver configuration, OS installation, application management, and ongoing system administration. Supports **multiple architectures** (x86_64, AArch64, RISC-V 64) through a Hardware Abstraction Layer (HAL).

Inspired by [NVIDIA VibeTensor](https://github.com/NVlabs/vibetensor) — where LLM agents generated ~195K lines of system software without human code review. Supports any LLM provider via [LiteLLM](https://github.com/BerriAI/litellm): Anthropic, OpenAI, Ollama, Google Gemini, OpenRouter, Azure, and more.

**We don't write the kernel. The agents do.**

## Architecture

### Orchestration Flow

```
┌─────────────────────────────────────────────────────┐
│                  Orchestration Engine                │
│         (VibeTensor-style iterative loop)            │
│                                                     │
│   specify goals → decompose → agents generate diffs │
│   → validate (build + test) → accept/reject → loop  │
└──────────────┬──────────────────────────┬───────────┘
               │                          │
    ┌──────────▼──────────┐    ┌──────────▼──────────┐
    │   Kernel Agents     │    │    SLM Agents       │
    │                     │    │                     │
    │  Manager (1x)       │    │  Data Scientist (1x)│
    │  Architect (1x)     │    │  Model Arch (1x)    │
    │  Developer (4x)     │    │  Training (4x)      │
    │  Reviewer (1x)      │    │  Evaluation (1x)    │
    │  Tester (1x)        │    │  Quantization (1x)  │
    │  Integrator (1x)    │    │  Export (1x)        │
    └──────────┬──────────┘    └──────────┬──────────┘
               │                          │
    ┌──────────▼──────────┐    ┌──────────▼──────────┐
    │   Git Workspace     │    │   Validation Layer   │
    │  (kernels/{arch})   │    │                      │
    │                     │    │  Build Validator     │
    │  Agents collaborate │    │  Test Validator      │
    │  via branches +     │    │  Composition Check   │
    │  structured diffs   │    │  (Frankenstein Fx)   │
    └─────────────────────┘    └──────────────────────┘
```

### Complete System Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                         AUTON System                               │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │              Kernel Development Workflow                  │     │
│  │                                                           │     │
│  │  Manager → Architect → Developers (4x parallel)          │     │
│  │     ↓          ↓            ↓                             │     │
│  │  Reviewer → Tester → Integrator                          │     │
│  │     ↓          ↓            ↓                             │     │
│  │  [Build Validator] [Test Validator] [Composition Check]  │     │
│  │                      ↓                                    │     │
│  │              kernels/{arch}/kernel.bin                   │     │
│  └──────────────────────────────────────────────────────────┘     │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │              SLM Training Workflow                        │     │
│  │                                                           │     │
│  │  Data Scientist → Model Architect                        │     │
│  │        ↓               ↓                                  │     │
│  │  [Dataset Prep]  [Architecture Design]                   │     │
│  │        ↓               ↓                                  │     │
│  │  Training Agents (4x parallel) → Evaluation Agent        │     │
│  │        ↓                              ↓                   │     │
│  │  Quantization Agent → Export Agent                       │     │
│  │        ↓                   ↓                              │     │
│  │    [INT4/INT8]      [GGUF/ONNX]                          │     │
│  │        └───────────────┬───────────┘                     │     │
│  │                        ↓                                  │     │
│  │              SLM/models/auton-slm                        │     │
│  └──────────────────────────────────────────────────────────┘     │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │              Integration & Deployment                     │     │
│  │                                                           │     │
│  │  kernel.bin + auton-slm.gguf                             │     │
│  │         ↓                                                 │     │
│  │  [SLM Integration Agent]                                 │     │
│  │         ↓                                                 │     │
│  │  Bootable SLM-Driven Kernel                              │     │
│  │         ↓                                                 │     │
│  │  [QEMU Validation] → Serial Output Analysis              │     │
│  │         ↓                                                 │     │
│  │  ✓ Boot  ✓ Hardware Discovery  ✓ Driver Loading         │     │
│  │         ↓                                                 │     │
│  │  [Release Builder] → ISO/IMG/QCOW2 Generation            │     │
│  │         ↓                                                 │     │
│  │  GitHub Release (auton-{arch}-{version}.iso)             │     │
│  └──────────────────────────────────────────────────────────┘     │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │              Test Coverage & Validation                   │     │
│  │                                                           │     │
│  │  Unit Tests (36 files)                                   │     │
│  │    ├─ Agents (11)      ├─ LLM (4)                        │     │
│  │    ├─ Orchestrator (4) ├─ Validation (3)                 │     │
│  │    └─ Comms (3)        └─ Other (11)                     │     │
│  │                                                           │     │
│  │  Integration Tests (4 files)                             │     │
│  │    ├─ Kernel Workflow  ├─ SLM Workflow                   │     │
│  │    └─ Dual Workflow    └─ Agent Collaboration            │     │
│  │                                                           │     │
│  │  Rust Tests (9 files)                                    │     │
│  │    ├─ Diff Validator (2)  ├─ Kernel Builder (3)          │     │
│  │    └─ Test Runner (3)                                    │     │
│  │                                                           │     │
│  │  SLM Tests (9 files)                                     │     │
│  │    ├─ Dataset/Tokenizer  ├─ Train/Evaluate               │     │
│  │    └─ Quantize/Export                                    │     │
│  │                                                           │     │
│  │  Acceptance Tests (kernel_spec/tests/)                   │     │
│  │    └─ Full QEMU validation per architecture              │     │
│  └──────────────────────────────────────────────────────────┘     │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │              Multi-Architecture Support                   │     │
│  │                                                           │     │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐               │     │
│  │  │  x86_64  │  │ AArch64  │  │ RISC-V   │               │     │
│  │  │          │  │          │  │          │               │     │
│  │  │Multiboot2│  │ DTB/UEFI │  │ OpenSBI  │               │     │
│  │  │   NASM   │  │  GNU AS  │  │  GNU AS  │               │     │
│  │  │   ACPI   │  │   DTB    │  │   DTB    │               │     │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘               │     │
│  │       └─────────────┴─────────────┘                      │     │
│  │                     │                                     │     │
│  │          Hardware Abstraction Layer (HAL)                │     │
│  │                     │                                     │     │
│  │       ┌─────────────┴─────────────┐                      │     │
│  │       │   Portable Kernel Core    │                      │     │
│  │       │  (Memory, Sched, IPC, FS) │                      │     │
│  │       └───────────────────────────┘                      │     │
│  └──────────────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────────────┘
```

## Agents

### Kernel Development Agents

| Agent | Role | Count |
|-------|------|-------|
| **Manager** | Decomposes goals into tasks, tracks dependencies, detects blocked paths | 1 |
| **Architect** | Designs subsystem interfaces, writes header files, resolves conflicts | 1 |
| **Developer** | Writes kernel C/ASM code, builds, tests, commits on feature branches | 4 parallel |
| **Reviewer** | Reviews diffs for correctness, memory safety, spec compliance | 1 |
| **Tester** | Writes tests, runs QEMU validation, detects composition failures | 1 |
| **Integrator** | Merges approved branches, runs full integration checks | 1 |

### SLM Training Agents

| Agent | Role | Count |
|-------|------|-------|
| **Data Scientist** | Prepares and analyzes training datasets, tokenization | 1 |
| **Model Architect** | Designs SLM architecture, estimates FLOPs, validates configs | 1 |
| **Training Agent** | Trains SLM models with distributed training support | 4 parallel |
| **Evaluation Agent** | Evaluates model checkpoints, tracks metrics | 1 |
| **Quantization Agent** | Quantizes models to INT4/INT8 for deployment | 1 |
| **Export Agent** | Exports models to GGUF/ONNX formats | 1 |

Agents communicate through **git branches and file-based messaging** — no message broker needed. The VibeTensor insight: treat agents as black boxes, validate only through builds and tests.

## Kernel Target

The agents build a custom **SLM-driven kernel from scratch** — Linux-inspired architecture with a custom API, portable across multiple architectures via a HAL. The embedded SLM drives the entire OS lifecycle:

1. **Boot** → SLM initializes
2. **Hardware Discovery** → SLM probes and identifies devices
3. **Driver Configuration** → SLM determines and loads needed drivers
4. **Installation** → SLM sets up filesystems, network, base system
5. **Application Setup** → SLM installs/configures apps based on device purpose
6. **Runtime Management** → SLM stays resident for ongoing admin, updates, troubleshooting

### Supported Architectures

| Architecture | Boot Protocol | Assembler | Firmware | Core Drivers |
|-------------|---------------|-----------|----------|-------------|
| **x86_64** | Multiboot2 | NASM | ACPI | 16550A UART, VGA, PIT, PS/2 |
| **AArch64** | DTB/UEFI | GNU AS | Device Tree | PL011 UART, GICv2, ARM Timer |
| **RISC-V 64** | OpenSBI + DTB | GNU AS | Device Tree | ns16550 UART, PLIC, CLINT |

Set the target architecture in `config/auton.toml`:
```toml
[kernel]
arch = "aarch64"  # x86_64, aarch64, or riscv64
```

### Subsystems

- **Boot** — Architecture-specific boot protocol via HAL, hardware handoff to SLM
- **Memory Management** — Bitmap PMM, multi-level paging VMM via MMU HAL, slab allocator, SLM memory pool
- **Scheduler** — Preemptive round-robin with priority classes (KERNEL > SLM > SYSTEM > USER)
- **IPC** — Structured message passing, ring buffers, SLM command channel
- **Device Framework** — PCI enumeration, firmware parsing (ACPI or Device Tree), uniform driver interface, SLM-driven loading
- **SLM Runtime** — Pluggable architecture with two backends:
  - *Rule Engine* (default) — keyword matching, pattern rules, decision trees (works on any hardware)
  - *Neural Backend* (optional) — loads real models (GGUF/ONNX), CPU inference with INT4/INT8 quantization
- **Drivers** — Arch-specific core drivers (serial, console, timer, input) + portable SLM-managed drivers (storage, network, display, USB)
- **Filesystem** — VFS layer, initramfs, ext2, devfs, procfs
- **Network Stack** — Ethernet, ARP, IPv4, TCP/UDP, DHCP, DNS, HTTP
- **Package Manager** — tar+manifest format, dependency resolution, SLM-driven installation
- **System Services** — SLM-driven init system, logging, resource monitoring

## Tech Stack

- **Python** — Agent orchestration framework
- **Rust** — Build tooling, diff validation, QEMU test runner
- **LiteLLM** — Multi-provider LLM abstraction (Anthropic, OpenAI, Ollama, Gemini, OpenRouter, Azure)
- **Git** — Agent collaboration and version control
- **QEMU** — Kernel testing and validation
- **Pytest** — Comprehensive unit and integration testing

## Setup

```bash
# Clone
git clone https://github.com/EdWelsh/AUTON.git
cd AUTON/agent

# Install
pip install -e .

# Configure — copy the example and add your API key(s)
cp config/auton.toml.example config/auton.toml
# Edit config/auton.toml with your keys, or use environment variables:
export ANTHROPIC_API_KEY="sk-ant-..."   # for Anthropic models
# export OPENAI_API_KEY="sk-..."        # for OpenAI models
# No key needed for Ollama (local)

# Run
auton run "Build a bootable kernel with SLM rule engine that detects hardware via PCI scan"
```

### Model Configuration

Models use `provider/model` format. Mix providers per agent role for cost optimization:

```toml
[llm]
model = "anthropic/claude-opus-4-6"    # default for all agents

[llm.api_keys]
anthropic = "sk-ant-..."
openai = "sk-..."

[agents.models]
developer = "anthropic/claude-sonnet-4-5-20250929"  # cheaper for code gen
reviewer = "openai/gpt-4o"                          # use a different provider
# tester = "ollama/llama3.1"                        # free, local
```

## Releases

AUTON automatically generates bootable images for all supported architectures:

- **ISO Images** — Bootable CD/DVD images for x86_64
- **Raw Disk Images** — `.img` files for USB/SD card deployment
- **QCOW2 Images** — QEMU-optimized virtual disk images
- **Embedded Binaries** — Standalone kernel binaries with embedded SLM

Releases are published as GitHub releases with artifacts for each architecture:
```
auton-x86_64-v0.1.0.iso
auton-x86_64-v0.1.0.img
auton-aarch64-v0.1.0.img
auton-riscv64-v0.1.0.img
```

Each release includes:
- Bootable kernel with embedded SLM
- Architecture-specific drivers
- Validation test results
- Build metadata and checksums

## Testing

AUTON includes a comprehensive test suite:

```bash
# Run unit tests
pytest agent/tests/unit/ -v

# Run with coverage
pytest agent/tests/unit/ --cov=orchestrator --cov-report=html

# Run integration tests
pytest agent/tests/integration/ -v

# Run Rust tool tests
cd agent/tools && cargo test

# Run SLM pipeline tests
pytest SLM/tests/ -v
```

### Test Structure
- **Unit Tests** (`agent/tests/unit/`) — Fast, isolated tests with mocks (36 test files)
- **Integration Tests** (`agent/tests/integration/`) — Multi-component workflow tests
- **Acceptance Tests** (`agent/kernel_spec/tests/`) — Full kernel validation in QEMU
- **Rust Tests** (`agent/tools/*/tests/`) — Build tool validation (9 test files)
- **SLM Tests** (`SLM/tests/`) — Training pipeline tests (9 test files)

## How It Works

1. **Manager** reads kernel specs and decomposes the goal into a dependency-ordered task graph
2. **Architect** designs subsystem interfaces as C header files
3. **Developers** (in parallel) implement code on feature branches, iterating: write → build → fix → test → commit
4. **Reviewer** checks each branch for correctness, memory safety, and composition risks
5. **Tester** validates in QEMU — boots the kernel, parses serial output for test results
6. **Integrator** merges approved branches, runs full integration suite
7. **Composition Validator** detects the "Frankenstein effect" — subsystems that pass in isolation but fail when combined
8. Loop until all tasks complete or budget exhausted

## Key Concepts

### SLM-Driven OS
The kernel embeds a Small Language Model as its central intelligence. The SLM is **pluggable**: a lightweight rule-based engine runs on minimal hardware (IoT, embedded), while systems with sufficient resources can load a real neural language model for richer understanding. Everything flows through the SLM — from first boot to ongoing system management.

### The Frankenstein Effect
From NVIDIA VibeTensor: *"Locally correct subsystems interact to yield globally suboptimal performance."* AUTON's Composition Validator specifically detects this by comparing unit test results against integration test results.

### Agents as Black Boxes
The orchestrator doesn't care how agents solve problems — only whether the result builds and passes tests. This is the VibeTensor methodology: validation through tools, not human review.

### SLM Intent System
All SLM interactions go through an intent classifier: `HARDWARE_IDENTIFY`, `DRIVER_SELECT`, `INSTALL_CONFIGURE`, `APP_INSTALL`, `SYSTEM_MANAGE`, `TROUBLESHOOT`. This allows the SLM to understand what the system needs at any point and dispatch the right kernel operations.

## License

**Source Available** — Free for personal, educational, and non-production use. Production and enterprise use requires a [commercial license or public attribution](LICENSE.md).

## References

- [NVIDIA VibeTensor](https://github.com/NVlabs/vibetensor) — AI-generated deep learning runtime
- [VibeTensor Paper](https://arxiv.org/abs/2601.16238) — *"System Software for Deep Learning, Fully Generated by AI Agents"*
- [AIOS](https://github.com/agiresearch/AIOS) — LLM Agent Operating System
- [LiteLLM](https://github.com/BerriAI/litellm) — Unified LLM API for 100+ providers


## Inspirations from our greatest of grand parents
The more I study, the more insatiable do I feel my genius for it to be

That brain of mine is something more than merely mortal; as time will show

I believe myself to possess a most singular combination of qualities exactly fitted to make me pre-eminently a discoverer of the hidden realities of nature.

The Analytical Engine has no pretensions whatever to originate anything. It can do whatever we know how to order it to perform.

The intellectual, the moral, the religious seem to me all naturally bound up and interlinked together in one great and harmonious whole.

I have an inexpressible wish to understand what has actually occurred.