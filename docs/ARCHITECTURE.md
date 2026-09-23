# Architecture

How AUTON is put together. For what it currently *does*, see
[the README's status section](../README.md#status); for what is unfinished, see
[`OPEN-WORK.md`](./OPEN-WORK.md).

These diagrams describe the orchestration system that writes the kernel. The
kernel itself is specified in [`agent/kernel_spec/`](../agent/kernel_spec/) and
does not live in this repository — see
[Why there is no kernel here](../README.md#why-there-is-no-kernel-here).

## Orchestration flow

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

## Complete system

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
│  │  Unit Tests (79 files)                                   │     │
│  │    ├─ Agents (12)      ├─ LLM (6)                        │     │
│  │    ├─ Orchestrator (8) ├─ Validation (3)                 │     │
│  │    └─ Comms (4)        └─ Top level (46)                 │     │
│  │                                                           │     │
│  │  Integration Tests (5 files)                             │     │
│  │    ├─ Kernel Workflow  ├─ SLM Workflow                   │     │
│  │    └─ Dual Workflow    └─ Agent Collaboration            │     │
│  │                                                           │     │
│  │  Rust Tests (10 files)                                   │     │
│  │    ├─ Diff Validator      ├─ Kernel Builder              │     │
│  │    └─ Test Runner                                        │     │
│  │                                                           │     │
│  │  SLM Tests (16 files)                                    │     │
│  │    ├─ Dataset/Tokenizer  ├─ Train/Evaluate               │     │
│  │    └─ Quantize/Export                                    │     │
│  │                                                           │     │
│  │  Acceptance Tests (kernel_spec/tests/)                   │     │
│  │    └─ Full QEMU validation per architecture              │     │
│  │                                                           │     │
│  │  Host gate suites (tests/kernel/run_*.sh, 22)            │     │
│  │    ├─ Frozen before a generation run                     │     │
│  │    ├─ exit 2 = not generated, 1 = wrong, 0 = pass        │     │
│  │    └─ 10 scored by injected bugs                         │     │
│  └──────────────────────────────────────────────────────────┘     │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │       Multi-Architecture Support (see note below)         │     │
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

### Kernel development agents

| Agent | Role | Count |
|-------|------|-------|
| **Manager** | Decomposes goals into tasks, tracks dependencies, detects blocked paths | 1 |
| **Architect** | Designs subsystem interfaces, writes header files, resolves conflicts | 1 |
| **Developer** | Writes kernel C/ASM code, builds, tests, commits on feature branches | 4 parallel |
| **Reviewer** | Reviews diffs for correctness, memory safety, spec compliance | 1 |
| **Tester** | Writes tests, runs QEMU validation, detects composition failures | 1 |
| **Integrator** | Merges approved branches, runs full integration checks | 1 |

### SLM training agents

| Agent | Role | Count |
|-------|------|-------|
| **Data Scientist** | Prepares and analyzes training datasets, tokenization | 1 |
| **Model Architect** | Designs SLM architecture, estimates FLOPs, validates configs | 1 |
| **Training Agent** | Trains SLM models with distributed training support | 4 parallel |
| **Evaluation Agent** | Evaluates model checkpoints, tracks metrics | 1 |
| **Quantization Agent** | Quantizes models to INT4/INT8 for deployment | 1 |
| **Export Agent** | Exports models to GGUF/ONNX formats | 1 |

Agents communicate through **git branches and file-based messaging** — no message broker needed. The VibeTensor insight: treat agents as black boxes, validate only through builds and tests.

## A note on architecture support

The HAL and the architecture registry
([`agent/orchestrator/arch_registry.py`](../agent/orchestrator/arch_registry.py))
carry profiles for **x86_64**, **aarch64** and **riscv64**, and each has a
specification under [`agent/kernel_spec/arch/`](../agent/kernel_spec/arch/).

That is not the same as support, so the diagram above says what is *designed*
rather than what runs:

| Architecture | Registry profile | Spec | End-to-end spine |
|---|---|---|---|
| x86_64 | yes | `arch/x86_64.md` | yes — full spine, the default |
| aarch64 | yes | `arch/aarch64.md` | boot spine only (build, boot, markers) |
| riscv64 | yes | `arch/riscv64.md` | **no** |

`scripts/e2e.sh --arch` accepts `x86_64` and `aarch64` and rejects anything
else. The model stages are x86-only by specification (`slm.md`), which is why
aarch64 runs the boot spine rather than the whole one — a spine that pretended
otherwise would report a pass for stages it never ran.
