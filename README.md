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
    │   Git Workspace     │    │   Git Workspace     │
    │  (kernels/{arch})   │    │     (SLM/)          │
    │                     │    │                     │
    │  Agents collaborate │    │  Agents collaborate │
    │  via branches +     │    │  via branches +     │
    │  structured diffs   │    │  structured diffs   │
    └──────────┬──────────┘    └──────────┬──────────┘
               │                          │
               └──────────┬───────────────┘
                          │
               ┌──────────▼──────────┐
               │   Validation Layer   │
               │                      │
               │  Build Validator     │
               │  Test Validator      │
               │  Composition Check   │
               │  (Frankenstein Fx)   │
               └──────────────────────┘
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

## SLM Training Data

The SLM is trained on OS-specific tasks to understand hardware, drivers, and system administration. Training datasets follow a structured format:

### Dataset Structure

```json
{
  "text": "Initialize PCI device at bus 0 device 3 function 0",
  "intent": "HARDWARE_IDENTIFY",
  "context": {
    "device_type": "network",
    "vendor_id": "0x8086",
    "device_id": "0x100e"
  }
}
```

### Intent Categories

- **HARDWARE_IDENTIFY** — Device detection, PCI enumeration, hardware probing
  - Examples: "Detect network card", "Scan PCI bus", "Identify storage controller"
- **DRIVER_SELECT** — Driver matching, module loading, driver configuration
  - Examples: "Load e1000 driver for Intel NIC", "Select AHCI driver for SATA"
- **INSTALL_CONFIGURE** — System setup, filesystem creation, network configuration
  - Examples: "Create ext2 filesystem", "Configure DHCP client", "Mount root partition"
- **APP_INSTALL** — Package installation, dependency resolution, service setup
  - Examples: "Install web server", "Resolve package dependencies", "Configure systemd service"
- **SYSTEM_MANAGE** — Runtime administration, resource monitoring, updates
  - Examples: "Check memory usage", "Update kernel modules", "Monitor disk space"
- **TROUBLESHOOT** — Error diagnosis, log analysis, recovery procedures
  - Examples: "Diagnose boot failure", "Analyze kernel panic", "Recover from disk error"

### Dataset Sources

- **Kernel Documentation** — Linux kernel docs, driver specifications, hardware manuals
- **System Logs** — Boot logs, dmesg output, hardware detection sequences
- **Command Traces** — Shell commands for hardware setup, driver loading, system configuration
- **Hardware Databases** — PCI ID databases, device compatibility lists, driver mappings
- **Troubleshooting Guides** — Common issues, error messages, recovery procedures

### Data Preparation Pipeline

```bash
# 1. Collect raw data
python SLM/tools/dataset_builder.py collect \
  --sources kernel_docs,pci_ids,boot_logs \
  --output SLM/datasets/raw/

# 2. Tokenize and process
python SLM/tools/tokenizer.py \
  --input SLM/datasets/raw/ \
  --output SLM/datasets/processed/ \
  --vocab-size 32000

# 3. Create train/validation splits
python SLM/tools/dataset_builder.py split \
  --input SLM/datasets/processed/ \
  --train-ratio 0.9 \
  --output SLM/datasets/
```

### Example Training Samples

```json
[
  {
    "text": "Detected Intel 82540EM Gigabit Ethernet Controller",
    "intent": "HARDWARE_IDENTIFY",
    "next_action": "Load e1000 network driver"
  },
  {
    "text": "Load e1000 driver for network interface",
    "intent": "DRIVER_SELECT",
    "driver": "e1000",
    "device_class": "network"
  },
  {
    "text": "Configure network interface with DHCP",
    "intent": "INSTALL_CONFIGURE",
    "protocol": "dhcp",
    "interface": "eth0"
  }
]
```

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
- **PyTorch** — Neural SLM backend (training, quantization, ONNX/GGUF export)
- **Pytest** — Comprehensive unit and integration testing

## Quick Start (Docker)

The fastest way to build and boot the kernel — no host toolchain required (the
image carries the cross toolchain, GRUB, and QEMU):

```bash
# Build the seed kernel and boot it in QEMU (serial console)
docker compose run os

# Boot + verify the acceptance serial markers
docker compose run acceptance

# Orchestrator unit tests + Rust tools + (torch-free) SLM tests
docker compose run test

# Full SLM neural pipeline tests (pulls in PyTorch; heavier image)
docker compose run slm
```

`docker compose run os` builds a Multiboot2 GRUB rescue ISO from the seed kernel
and boots it via `qemu-system-x86_64 -cdrom ... -serial stdio`, printing the
full boot sequence through `[SLM] Ready` and `[BOOT] OK`. The image is pinned to
`linux/amd64` (GRUB PC/BIOS + x86 QEMU); on Apple Silicon it runs emulated.

> The seed kernel lives in `kernels/x86_64/` and is the buildable scaffold the
> agents extend. The neural on-device SLM chat is layered on top of this
> foundation (see the plans under `.claude/PRPs/plans/`).

## The OS is the chat — no terminal

AUTON boots straight into an `auton>` prompt over the serial console. You
configure the machine it runs on by *asking*, not by running shell commands.
Networking comes up at boot (DHCP over an in-kernel IPv4 stack), and the chat
can turn the box into a server role:

```text
auton> what is my ip
My IP is 10.0.2.15 (gateway 10.0.2.2, dns 10.0.2.3).
auton> what can you do
I can turn this machine into a server role from chat:
  web server - ready
  DNS server - ready
  file server - roadmap
  email server - roadmap
  database server - roadmap
  SSH server - roadmap
  DHCP server - roadmap
auton> be a web server
Configuring this machine as a web server (in-kernel HTTP on port 80)...
[HTTP] listening on :80
```

System queries answered from live kernel state: `what is my ip`, `hostname`
(and `set hostname web1`), `memory`, `devices`, `uptime`, `status`. Working
roles run on the in-kernel TCP/IP stack; roadmap roles report what they still
need. Everything is a chat sentence — there is no shell.

Try it with host networking and a forwarded port:

```bash
# Boot with a SLIRP-backed NIC and forward host :8080 -> guest :80
docker compose run --rm os bash -lc \
  'cd kernels/x86_64 && make CC=gcc iso && \
   qemu-system-x86_64 -cdrom build/auton.iso -serial stdio -display none \
     -no-reboot -m 128M -nic user,model=e1000,hostfwd=tcp::8080-:80'
# then in the prompt: be a web server   (fetch http://localhost:8080)
```

`docker compose run acceptance` also verifies this automatically: alongside the
boot markers it runs `net_dhcp_ip` (a real DHCP lease) and `http_get` (a real
HTTP 200 from the in-kernel web server). Set `SKIP_NET=1` to skip the network
checks in environments without user-mode networking.

### On-device model (optional)

With a trained model bundled as a boot module and ≥128 MB RAM, the chat answers
with a transformer running **on the machine itself** (falling back to the rule
engine otherwise):

```bash
# Train + export a tiny model on the host (see SLM/scripts), then:
make -C kernels/x86_64 run-neural MODEL=/path/to/auton-slm.bin   # boots with -m 256M
# boot shows: [SLM] Loaded model ... / [SLM] Backend: neural
```

## Setup (orchestrator)

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

Build a versioned, bootable GRUB rescue ISO of the seed kernel:

```bash
# Produces dist/auton-x86_64-v0.1.0.iso (runs inside the Docker toolchain)
docker compose run --rm os bash scripts/build-iso.sh x86_64 v0.1.0

# Boot a built ISO directly:
qemu-system-x86_64 -cdrom dist/auton-x86_64-v0.1.0.iso -serial stdio -display none
```

The ISO boots through the full sequence to `[SLM] Ready` / `[BOOT] OK`, the same
markers `docker compose run acceptance` verifies.

**Shipped today:** x86_64 bootable ISO (`scripts/build-iso.sh`).

**Roadmap (not yet shipped):** raw `.img`/QCOW2 disk images, AArch64/RISC-V seed
kernels, automated GitHub release publishing, and a neural (GGUF/ONNX) in-kernel
SLM. The build system and Docker image are parameterized by `ARCH`, but only
x86_64 is currently brought to "boots + passes acceptance".

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

# Run SLM pipeline tests (neural train/export tests auto-skip without torch;
# install SLM/requirements.txt to run the full pipeline)
PYTHONPATH=SLM pytest SLM/tests/ -v
```

### Test Structure
- **Unit Tests** (`agent/tests/unit/`) — Fast, isolated tests with mocks (36 test files)
- **Integration Tests** (`agent/tests/integration/`) — Multi-component workflow tests
- **Acceptance Tests** (`agent/kernel_spec/tests/`) — Full kernel validation in QEMU
- **Rust Tests** (`agent/tools/*/tests/` + per-crate `src/lib.rs`) — build tool validation
- **SLM Tests** (`SLM/tests/`) — tools + neural train/eval/quantize/export pipeline (torch tests skip when torch is absent)

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