# AUTON

**Autonomous agent orchestration system that builds a natural language LLM agent-based hypervisor kernel from scratch.**

Inspired by [NVIDIA VibeTensor](https://github.com/NVlabs/vibetensor) — where LLM agents generated ~195K lines of system software without human code review — AUTON uses Claude API to power a team of specialized agents that collaboratively write, review, test, and integrate a custom x86_64 kernel.

**We don't write the kernel. The agents do.**

## Architecture

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
    │     Agent Team      │    │   Validation Layer   │
    │                     │    │                      │
    │  Manager (1x)       │    │  Build Validator     │
    │  Architect (1x)     │    │  Test Validator      │
    │  Developer (4x)     │    │  Composition Check   │
    │  Reviewer (1x)      │    │  (Frankenstein Fx)   │
    │  Tester (1x)        │    │                      │
    │  Integrator (1x)    │    └──────────────────────┘
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │   Git Workspace     │
    │  (shared repo)      │
    │                     │
    │  Agents collaborate │
    │  via branches +     │
    │  structured diffs   │
    └─────────────────────┘
```

## Agents

| Agent | Role | Count |
|-------|------|-------|
| **Manager** | Decomposes goals into tasks, tracks dependencies, detects blocked paths | 1 |
| **Architect** | Designs subsystem interfaces, writes header files, resolves conflicts | 1 |
| **Developer** | Writes kernel C/ASM code, builds, tests, commits on feature branches | 3–6 parallel |
| **Reviewer** | Reviews diffs for correctness, memory safety, spec compliance | 1–2 |
| **Tester** | Writes tests, runs QEMU validation, detects composition failures | 1–2 |
| **Integrator** | Merges approved branches, runs full integration checks | 1 |

Agents communicate through **git branches and file-based messaging** — no message broker needed. The VibeTensor insight: treat agents as black boxes, validate only through builds and tests.

## Kernel Target

The agents build a custom **x86_64 kernel from scratch** with:

- **Boot** — Multiboot2, GDT/IDT, real→protected→long mode
- **Memory Management** — Bitmap page allocator, 4-level paging, slab allocator
- **Scheduler** — Preemptive round-robin with LLM-aware priority classes
- **IPC** — Natural language message passing between agents
- **NL Syscall** — Natural language syscall interface (the core innovation)
- **Hypervisor** — Agent VM isolation with capability-based security
- **LLM Runtime** — In-kernel NL processing (keyword matching → future: neural)

## Tech Stack

- **Python** — Agent orchestration framework
- **Rust** — Build tooling, diff validation, QEMU test runner
- **Claude API** (Anthropic) — Powers all agent reasoning
- **Git** — Agent collaboration and version control
- **QEMU** — Kernel testing and validation

## Setup

```bash
# Clone
git clone https://github.com/EdWelsh/AUTON.git
cd AUTON

# Set up the agent directory (not tracked in git)
mkdir -p agent
# Copy the orchestration framework into agent/
# (see deployment instructions)

# Install
cd agent
pip install -e .

# Configure
export ANTHROPIC_API_KEY="sk-ant-..."
# Or edit agent/config/auton.toml

# Run
auton run "Build a minimal bootable x86_64 kernel that prints to serial console"
```

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

### The Frankenstein Effect
From NVIDIA VibeTensor: *"Locally correct subsystems interact to yield globally suboptimal performance."* AUTON's Composition Validator specifically detects this by comparing unit test results against integration test results.

### Agents as Black Boxes
The orchestrator doesn't care how agents solve problems — only whether the result builds and passes tests. This is the VibeTensor methodology: validation through tools, not human review.

### Natural Language Kernel
The kernel itself uses natural language as its primary interface. Instead of `syscall(SYS_mmap, ...)`, agents say `"allocate 4KB of memory"` and the NL syscall layer parses intent into kernel operations.

## License

Apache 2.0

## References

- [NVIDIA VibeTensor](https://github.com/NVlabs/vibetensor) — AI-generated deep learning runtime
- [VibeTensor Paper](https://arxiv.org/abs/2601.16238) — *"System Software for Deep Learning, Fully Generated by AI Agents"*
- [AIOS](https://github.com/agiresearch/AIOS) — LLM Agent Operating System
