# AUTON Project Structure

## Root Directory Organization

```
AUTON/
├── agent/                    # Core orchestration system
├── kernels/                  # Generated kernel outputs by architecture
├── SLM/                      # SLM training and model management
├── .auton/                   # Runtime state and task tracking
├── .amazonq/                 # IDE integration and rules
├── README.md                 # Project documentation
├── PHASES.md                 # Implementation roadmap
└── LICENSE.md                # Licensing information
```

## Core Components

### Agent Orchestration (`agent/`)
```
agent/
├── orchestrator/             # Main orchestration engine
│   ├── agents/              # Agent implementations
│   ├── core/                # Core orchestration logic
│   ├── llm/                 # LLM integration and tools
│   ├── comms/               # Agent communication
│   └── validation/          # Build and test validation
├── kernel_spec/             # Kernel specifications
│   ├── arch/                # Architecture-specific specs
│   ├── subsystems/          # Kernel subsystem specs
│   └── tests/               # Acceptance tests
├── slm_spec/                # SLM training specifications
├── config/                  # Configuration files
├── tools/                   # Rust build tools
│   ├── diff-validator/      # Diff validation (+ tests/)
│   ├── kernel-builder/      # Build system (+ tests/)
│   └── test-runner/         # QEMU runner (+ tests/)
├── workspace/               # Git workspace for agents
└── tests/                   # Unit and integration tests
    ├── unit/                # Fast isolated tests (36 files)
    ├── integration/         # Multi-component tests (4 files)
    ├── fixtures/            # Mocks and test data
    └── conftest.py          # Pytest configuration
```

### Kernel Outputs (`kernels/`)
```
kernels/
├── x86_64/                  # x86_64 kernel builds
├── aarch64/                 # ARM64 kernel builds
└── riscv64/                 # RISC-V kernel builds
```

### SLM Pipeline (`SLM/`)
```
SLM/
├── models/                  # Model storage
│   ├── checkpoints/         # Training checkpoints
│   ├── quantized/           # Quantized models
│   └── exports/             # GGUF/ONNX exports
├── datasets/                # Training data
│   ├── raw/                 # Raw datasets
│   ├── processed/           # Tokenized data
│   └── benchmarks/          # Evaluation datasets
├── configs/                 # Model configurations
├── scripts/                 # Training/export scripts
├── tools/                   # Data processing utilities
├── tests/                   # SLM pipeline tests (9 files)
├── fixtures/                # Test datasets and configs
└── notebooks/               # Jupyter analysis notebooks
```

## Architectural Patterns

### Agent Collaboration Architecture
```
┌─────────────────────────────────────────────────────┐
│                Orchestration Engine                 │
│         (VibeTensor-style iterative loop)           │
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

### Multi-Architecture HAL Design
```
┌─────────────────────────────────────────────────────┐
│                 Kernel Subsystems                   │
│  (Memory, Scheduler, IPC, Filesystem, Network)      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│            Hardware Abstraction Layer               │
│                      (HAL)                          │
└─────┬──────────────┬──────────────┬─────────────────┘
      │              │              │
┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
│   x86_64  │  │  AArch64  │  │ RISC-V 64 │
│           │  │           │  │           │
│ Multiboot2│  │ DTB/UEFI  │  │OpenSBI+DTB│
│   NASM    │  │  GNU AS   │  │  GNU AS   │
│   ACPI    │  │Device Tree│  │Device Tree│
└───────────┘  └───────────┘  └───────────┘
```

### SLM Integration Architecture
```
┌─────────────────────────────────────────────────────┐
│                 Kernel Runtime                      │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │              SLM Runtime                    │    │
│  │                                             │    │
│  │  ┌─────────────┐    ┌─────────────────┐    │    │
│  │  │Rule Engine  │    │ Neural Backend  │    │    │
│  │  │(default)    │    │   (optional)    │    │    │
│  │  │             │    │                 │    │    │
│  │  │• Keywords   │    │• GGUF/ONNX     │    │    │
│  │  │• Patterns   │    │• INT4/INT8     │    │    │
│  │  │• Decision   │    │• CPU Inference │    │    │
│  │  │  Trees      │    │                 │    │    │
│  │  └─────────────┘    └─────────────────┘    │    │
│  │                                             │    │
│  │  Intent Classifier:                         │    │
│  │  HARDWARE_IDENTIFY | DRIVER_SELECT |       │    │
│  │  INSTALL_CONFIGURE | APP_INSTALL |         │    │
│  │  SYSTEM_MANAGE | TROUBLESHOOT              │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  Hardware Discovery → Driver Config → Installation  │
│  → App Management → Runtime Administration          │
└─────────────────────────────────────────────────────┘
```

## Key Relationships

### Agent Dependencies
- **Manager** → decomposes goals → **Architect** + **Developers**
- **Architect** → designs interfaces → **Developers** implement
- **Developers** → write code → **Reviewer** validates
- **Reviewer** → approves → **Tester** validates
- **Tester** → passes → **Integrator** merges
- **Integrator** → detects composition issues → feedback loop

### Configuration Flow
- `auton.toml` → Agent models, architecture, validation settings
- Architecture selection → HAL configuration → Agent prompts
- SLM configuration → Training pipeline → Kernel integration

### Data Flow
- Specifications → Agent prompts → Generated code → Git branches
- Build validation → Test results → Integration decisions
- SLM training → Model export → Kernel embedding