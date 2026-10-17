# AUTON

**An agent swarm that writes an operating system kernel — and a set of gates that decide whether it worked.**

AUTON uses LLM agents to write, review, test and integrate a kernel with a
**Small Language Model (SLM)** embedded in it. The SLM is meant to be the OS's
interface: you configure the machine by asking, not by running shell commands.

Inspired by [NVIDIA VibeTensor](https://github.com/NVlabs/vibetensor), where LLM
agents generated ~195K lines of system software without human code review. Any
provider works via [LiteLLM](https://github.com/BerriAI/litellm) — Anthropic,
OpenAI, Ollama, Gemini, OpenRouter, Azure.

**We don't write the kernel. The agents do.**

## Status

Honest version, as of 2026-10-17.

**What has been proved.** On 2026-09-22 a local model (`qwen3.5:27b`) wrote a
430-line TFTP server that passes **all 31 checks** of a host suite written by a
person, frozen before the run, and never present in the model's workspace
([report](.claude/PRPs/reports/w14-f6-qwen-report.md)). In the first full
generation campaign (finished 2026-10-10) the VirtIO console driver (R8) passed
its 29-check frozen gate.

**What has not.** The same campaign passed **1 of 12** runs. Eleven failures were
investigated one by one in
[`w24`](.claude/PRPs/plans/w24-campaign-failure-investigations.plan.md); most were
harness defects (suites using names no spec declared, git plumbing, timeouts),
now fixed and tested. A third attempt at R1 (the memory manager) was
pre-registered and started on 2026-10-17, then stopped by the owner to save
subscription usage before it produced a result.

| | |
|---|---|
| Generation runs passing every gate | TFTP (w14), **R8 VirtIO console** (campaign); 11 campaign runs failed |
| Host gate suites | **22** in [`tests/kernel/`](tests/kernel/); `run_mm_test.sh` and `run_play_doom_test.sh` also score themselves against injected bugs (`--inject`) |
| Agent roles | 13 roles, plus **24 specialists** (one per area of kernel creation) |
| Hardware knowledge | **5,164 vendors**, **284 processor models** across 5 architectures, 46 QEMU CPU models, every x86 CPUID feature bit in Linux's `cpufeatures.h` |
| SLM data | kernel set **1,572 rows**, 929 words (90 of the 1,019 word slots left); 30,848 host-side reference rows; 2.8M words of fetched domain text |
| Architectures with a full end-to-end spine | **1** (x86_64); aarch64 boots; riscv64 is specified only |
| CI | 2 workflows, 5 matrix legs: [see below](#continuous-integration) |

There is no finished kernel, and this README will not imply otherwise. What
exists is everything that *judges* a kernel: specifications, gates, oracles,
acceptance harnesses, hardware knowledge, and an orchestration loop. What
remains is running the swarm: see [`docs/OPEN-WORK.md`](docs/OPEN-WORK.md).

### Why there is no kernel here

`kernels/` is deliberately absent from this repository. It is generated output,
and it is in `.gitignore`. The premise of the project is that agents write the
kernel, so a kernel checked in alongside them would make every gate meaningless.

**This repository holds the agents that create kernels, not kernels.** Every tree
an agent writes lives in a testing or runtime area: a campaign run's workspace is
`.artifacts/campaign/<run>-attempt<k>/ws`, a vendor research run's is
`.artifacts/hardware/<run>/ws`, and both are gitignored. The only kernel C code
that is tracked is under [`tests/kernel/`](tests/kernel/): the frozen suites and
the hand-written reference implementations they are scored against.

What *is* here are **base trees**: tagged starting points an experiment can be
seeded from, so that a gate refusal means something. `kernel-base-v5` is the
current default.

```bash
# Materialise a kernel tree to build, boot or point a gate at
scripts/kernel-base.sh /tmp/tree          # or --rev kernel-base-v4
```

| Where to look | What it holds |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | how the orchestrator, agents and validation layers fit together |
| [`docs/OPEN-WORK.md`](docs/OPEN-WORK.md) | everything unfinished, its blocker, and the next step |
| [`auton-completion.prd.md`](.claude/PRPs/prds/completed/auton-completion.prd.md) | finishing what is defined: every remaining phase with the gate that decides it |
| [`auton-application-to-environment.prd.md`](.claude/PRPs/prds/completed/auton-application-to-environment.prd.md) | new scope: an Analyst agent reads an application repository and hands the swarm a manifest for the minimum environment that runs it |
| [`docs/GENERATION-QUEUE.md`](docs/GENERATION-QUEUE.md) | each generation run, its command, and the gate that decides it |
| [`docs/HOST-MATRIX.md`](docs/HOST-MATRIX.md) | what each host can build, boot and verify — and what it cannot |
| [`agent/kernel_spec/`](agent/kernel_spec/) | the kernel specification the agents are held to |
| [`agent/hardware/`](agent/hardware/README.md) | vendor inventory and registry, instruction-set tables, errata |
| [`docs/CAMPAIGN.md`](docs/CAMPAIGN.md) | how a generation campaign is run, budgeted and stopped |
| [`SLM/DATA.md`](SLM/DATA.md) | the data an in-kernel SLM needs, and what fits its tokenizer |
| [`w26` drift plan](.claude/PRPs/plans/w26-drift-and-slm-readiness.plan.md) | where docs, specs and code disagreed, what was fixed, what is left |
| [Wiki](https://github.com/EdWelsh/AUTON/wiki) | the same material as a guided tour (source in [`wiki/`](wiki/)) |

## Quick start

Everything below is run from a fresh clone. Pick the path that matches what you
want to do.

### I want to see the kernel boot

No host toolchain required; the image carries the cross toolchain, GRUB and QEMU.

```bash
git clone https://github.com/EdWelsh/AUTON.git
cd AUTON
scripts/kernel-base.sh kernels/x86_64     # the tree docker compose expects
docker compose run os                     # build + boot to the auton> prompt
docker compose run acceptance             # boot + verify the serial markers
```

The ISO is pinned to `linux/amd64` (GRUB PC/BIOS + x86 QEMU); on Apple Silicon
it runs emulated, which is slow but works.

### I want to build and boot natively (macOS or Linux)

Faster than Docker on Apple Silicon, because it avoids emulating x86 inside an
emulated `linux/amd64` container.

```bash
# macOS, one time
brew install qemu xorriso x86_64-elf-gcc x86_64-elf-binutils i686-elf-grub
# Linux, one time
# sudo apt install build-essential grub-pc-bin xorriso qemu-system-x86

git clone https://github.com/EdWelsh/AUTON.git
cd AUTON
scripts/preflight.sh                      # tools present, enough free disk
scripts/kernel-base.sh kernels/x86_64
scripts/auton-boot-native.sh              # build the ISO and boot to auton>
scripts/run-acceptance.sh                 # boot + verify the markers
```

> **`run-acceptance.sh` exits non-zero today, and that is correct.** 13 markers
> pass; one fails:
>
> ```
> FAIL  \[MM\] PMM initialized: \d+ pages total, \d+ reserved, \d+ free
> ```
>
> `mm.md` specifies a bitmap PMM and that exact line; the base still runs the
> seed's bump allocator. The marker is right and the base is behind it. This is
> recorded in [`docs/E2E-EXPECTED.yaml`](docs/E2E-EXPECTED.yaml), which CI
> checks — so a *new* failure is caught, and a stale expectation is too. You
> have not broken anything.

`scripts/lib/toolchain.sh` resolves per-platform tool names, so the same scripts
and Makefile work on both. Any `CC`, `GRUB_MKRESCUE` or `QEMU` you set is
respected. `scripts/preflight.sh` fails loudly when a tool is missing or free
disk is under `MIN_FREE_GB` (default 5) — a full volume has corrupted Docker
layers mid-build before.

### I want to run the agent swarm

```bash
git clone https://github.com/EdWelsh/AUTON.git
cd AUTON
python3 -m venv .venv && .venv/bin/pip install -e "agent[dev]"   # Python >= 3.11
cp agent/config/auton.toml.example agent/config/auton.toml

# Any LiteLLM provider (set its API key), a local Ollama model, or the Claude
# subscription through Claude Code (`claude-cli/<model>`, no API key).
cd agent && ../.venv/bin/auton run "Implement the memory manager specified in mm.md"
```

`auton` has four commands: `run`, `status`, `tasks`, `agents`. A run's tree goes
wherever `[workspace] path` points; the campaign and research scripts point it
into `.artifacts/`.

> **Before spending a run on a model, qualify it.**
> `scripts/model-probe.py <model>` puts it through four checks: tool calling,
> file fidelity, a 25k-character prompt, and a second turn. Four earlier runs on
> an unqualified model produced zero working lines.

> **Runs cost model calls.** On a subscription, a campaign run is hours of calls.
> `scripts/campaign.py --only <run>` runs one; stop it with Ctrl-C and resume
> later, losing nothing.

### I want to train the kernel's SLM

```bash
python SLM/tools/vocab_budget.py --together SLM/datasets/os_chat.jsonl SLM/datasets/hardware_kernel.jsonl
.venv/bin/python scripts/slm_run.py start chat-1 --goal "Train the kernel chat model"
.venv/bin/python scripts/slm_run.py status chat-1
```

The swarm builds the training set from ground truth, checks it fits the kernel tokenizer,
trains, exports to the AUTON format, proves parity with the kernel's forward pass, and scores
the chat eval. Read [`SLM/DATA.md`](SLM/DATA.md) for what data fits and why.

### I want to research hardware vendors

```bash
python agent/tools/vendor_registry.py --lookup 8086          # who is this vendor?
python agent/tools/isa_tables.py --has alderlake avx512f     # does this part have it?
python agent/tools/isa_tables.py --cpuid fma4                # how does software detect it?

# The vendor spec agents, in a testing area; then collect what passed its checks
.venv/bin/python scripts/vendor_research.py start scout-1 \
    --goal "Find the documentation for the 5 highest-priority vendors in vendor_queue"
.venv/bin/python scripts/vendor_research.py collect scout-1
```

### I want to run the tests

```bash
pytest agent/tests/unit/                          # orchestrator unit tests (~2,000)
pytest agent/tests/integration/                   # multi-component workflows
PYTHONPATH=SLM pytest SLM/tests/                  # SLM pipeline
cd controlplane && pytest                         # host control plane
cd agent/tools && cargo test                      # Rust build tooling

tests/kernel/run_mm_test.sh --self-test           # a host gate, against its reference
```

Torch-dependent SLM tests skip when torch is absent, and say so rather than
vanishing. Tests that need a live model skip when it is unreachable **or too
busy to answer** — see [`controlplane/tests/ollama_probe.py`](controlplane/tests/ollama_probe.py).

## The OS is the chat — no terminal

AUTON boots straight into an `auton>` prompt over the serial console. You
configure the machine by *asking*. Networking comes up at boot (DHCP over an
in-kernel IPv4 stack), and the chat can turn the box into a server role:

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

Queries are answered from live kernel state: `what is my ip`, `hostname` (and
`set hostname web1`), `memory`, `devices`, `uptime`, `status`. Roles marked
*ready* run on the in-kernel TCP/IP stack; *roadmap* roles report what they
still need instead of pretending. There is no shell.

Try it with a forwarded port:

```bash
scripts/kernel-base.sh kernels/x86_64

# Resolve the cross toolchain for this host. A bare `make` picks the host cc,
# which on macOS is arm64 clang and rejects the x86 flags outright.
source scripts/lib/toolchain.sh

make -C kernels/x86_64 CC="$CC" GRUB_MKRESCUE="$GRUB_MKRESCUE" iso
"$QEMU" -cdrom kernels/x86_64/build/auton.iso -serial stdio -display none \
    -no-reboot -m 128M -nic user,model=e1000,hostfwd=tcp::8080-:80
# then at the prompt: be a web server     (fetch http://localhost:8080)
```

`scripts/run-acceptance.sh` verifies this automatically: alongside the boot
markers it runs `net_dhcp_ip` (a real DHCP lease) and `http_get` (a real HTTP
200 from the in-kernel web server). `SKIP_NET=1` skips the network checks where
user-mode networking is unavailable.

### On-device model (optional)

With a trained model bundled as a boot module and >= 128 MB RAM, the chat can
answer with a transformer running on the machine itself, falling back to the
rule engine otherwise:

```bash
source scripts/lib/toolchain.sh
make -C kernels/x86_64 CC="$CC" GRUB_MKRESCUE="$GRUB_MKRESCUE" \
     run-neural MODEL=/path/to/auton-slm.bin        # boots with -m 256M
# boot shows: [SLM] Loaded model ... / [SLM] Backend: neural
```

> The end-to-end spine that trains, exports and checks this model against the
> in-kernel forward pass currently **fails at its parity stage** on every
> platform tested. See [`docs/OPEN-WORK.md`](docs/OPEN-WORK.md).

## How it works

1. **Manager** reads the kernel specs and decomposes the goal into a dependency-ordered task graph
2. **Architect** designs subsystem interfaces as C header files
3. **Developers and specialists** (in parallel) implement on feature branches: write → build → fix → test → commit
4. **Reviewer** checks each branch for correctness, memory safety and composition risk, with the checklist of every specialist whose files the change touches
5. **Tester** validates in QEMU: boots the kernel, parses serial output
6. **Integrator** merges approved branches and runs the full suite
7. **Composition Validator** detects the "Frankenstein effect": subsystems that pass alone and fail together
8. Loop until the tasks complete or the budget is spent

A syntax gate sits in front of step 4: code that does not compile never reaches
a reviewer. It exists because a model reviewer once approved a header with seven
syntax errors in it.

### Specialists: every aspect of kernel creation, not just the SLM

[`agent/kernel_spec/specialists.yaml`](agent/kernel_spec/specialists.yaml) defines
24 specialists, each with the specs it owns, the files it covers, what it knows
and a review checklist: boot, CPU features and instruction use, memory,
interrupts, timers, scheduling, SMP, locking and memory ordering, IPC, the
user/kernel boundary, device model and PCI, network / storage / console drivers,
filesystems, networking, hardening, silicon errata, ACPI, portability, the
toolchain, logging and panics, the on-device SLM, and network services. The
manager assigns work to `<id>_specialist`; `agents.specialists` turns them on
(`"all"` in the example config).

### Hardware knowledge, and the agents that grow it

A kernel has to know what it is running on, and a manual is not proof:

- **Vendor registry**, every vendor that has held a PCI, USB, x86 CPUID or Arm
  MIDR identity: 5,164, derived from `pci.ids`, `usb.ids` and the Linux kernel's
  identity tables ([`vendor_registry.py`](agent/tools/vendor_registry.py)).
- **Instruction-set tables**, which of 284 processor models implement which
  extensions, from LLVM's target definitions, plus each x86 feature's CPUID bit
  from Linux ([`isa_tables.py`](agent/tools/isa_tables.py)).
- **Exceptions**, where silicon disagrees with documents: an extension
  announced and never shipped (Intel FMA4), dropped later (FMA4, XOP and 3DNow!
  on Zen), fused off (AVX-512 on Alder Lake) or disabled by microcode (TSX).
  Each row is cited ([`isa/exceptions.yaml`](agent/hardware/isa/exceptions.yaml)).
  So the [`cpu`](agent/kernel_spec/subsystems/cpu.md) spec requires the kernel
  to use anything beyond the baseline only after the CPU says it has it.
- **Vendor spec agents.** The *Vendor Scout* finds what an uncovered vendor
  publishes and proposes inventory entries; the *Spec Reader* reads a fetched
  document and derives records whose quotes are checked against the cited page.
  Fetched documents stay in `.cache/vendor/`; nothing an agent writes becomes a
  fact until a person merges a record that passed its check.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the agent roster, the
full system diagram and the architecture-support matrix.

## How a generation run is judged

Every run is decided by gates **written before it starts** and frozen. This is
the part of the project that makes a result mean something.

- **Pre-register, then run once.** The gate, the prompt and the model are
  recorded before the run; the transcript is archived to `.artifacts/authorship/`.
- **Exit codes carry meaning.** `2` = not generated, `1` = generated wrong,
  `0` = pass. A suite that did not run has found nothing, and must never read as
  a pass.
- **Suites are scored by injected bugs.** Known defects are injected into a
  known-good implementation; every one must be caught, or the suite has a gap
  (`run_mm_test.sh --inject` scores 9/9).
- **Report either way.** Failed runs get a report with the same care as
  successful ones — see the
  [memory-manager report](.claude/PRPs/reports/w15-mm-qwen-report.md).

The gates live in [`tests/kernel/`](tests/kernel/) and run on the host, against
the specification, without the kernel needing to boot.

## Key concepts

### SLM-driven OS
The kernel embeds a Small Language Model as its interface. The SLM is
**pluggable**: a rule-based engine runs on minimal hardware, and systems with
enough resources can load a real neural model. Its training data is generated
from ground truth, never written, and must fit the kernel's word-level tokenizer
(1,024 words): `os_chat.jsonl` from what the kernel prints and `hardware_kernel.jsonl`
from the CPU every gate boots on. Facts come from lookup tables in the model file,
not from the model. See [`SLM/DATA.md`](SLM/DATA.md).

### The Frankenstein effect
From VibeTensor: *"Locally correct subsystems interact to yield globally
suboptimal performance."* The Composition Validator compares unit results
against integration results to catch it.

### Agents as black boxes
The orchestrator does not care how an agent solved a problem — only whether the
result builds and passes. Validation through tools, not human review.

## Tech stack

- **Python** (>= 3.11) — agent orchestration
- **Rust** — build tooling, diff validation, QEMU test runner
- **LiteLLM** — multi-provider LLM abstraction
- **Git** — how agents collaborate; there is no message broker
- **QEMU** — kernel testing and validation
- **PyTorch** — neural SLM backend (training, quantization, ONNX/GGUF export)
- **C / NASM / GNU AS** — the kernel the agents write

## Continuous integration

Two workflows, five matrix legs, all in [`.github/workflows/`](.github/workflows/):

| Workflow | Legs | What it covers |
|---|---|---|
| `controlplane` | ubuntu, macOS, Windows | the host control plane on all three hosts |
| `portability` | linux-x86_64, darwin-arm64, linux-e2e | unit suites, host gates, and the e2e spine |

The `portability` matrix exists because the hosts differ in what they can
prove: a Linux x86-64 runner executes the live CPUID cross-check that an arm64
Mac can only SKIP.

CI first ran on 2026-09-23 and was red, which was the point of running it. It
found four missing dependencies, four tests that passed only on a machine with
a warmed cache, a Windows process launcher that ate backslashes, a liveness
check that terminated the process it inspected, and a memory leak in a test
oracle that only LeakSanitizer on Linux can see. Not all of those are fixed —
[`docs/OPEN-WORK.md`](docs/OPEN-WORK.md) tracks what is left.

## Releases

```bash
docker compose run --rm os bash scripts/build-iso.sh x86_64 v0.1.0
qemu-system-x86_64 -cdrom dist/auton-x86_64-v0.1.0.iso -serial stdio -display none
```

**Shipped:** x86_64 bootable ISO via `scripts/build-iso.sh`.

**Not shipped:** raw `.img`/QCOW2 images, aarch64 and riscv64 seed kernels,
automated release publishing. The build system is parameterised by `ARCH`, but
only x86_64 is brought to "boots and passes acceptance".

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) first — this project has an
unusual rule that matters more than style: **a test must be able to fail.**
Bug reports and specification issues are as welcome as code.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). To
report a vulnerability, see [SECURITY.md](SECURITY.md).

## License

**Source Available** — free for personal, educational, academic and
non-production use. Production and enterprise use requires a commercial licence
or public attribution. See [LICENSE.md](LICENSE.md) for the terms; this is not
an OSI-approved open-source licence.

## References

- [NVIDIA VibeTensor](https://github.com/NVlabs/vibetensor) — AI-generated deep learning runtime
- [VibeTensor Paper](https://arxiv.org/abs/2601.16238) — *"System Software for Deep Learning, Fully Generated by AI Agents"*
- [AIOS](https://github.com/agiresearch/AIOS) — LLM Agent Operating System
- [LiteLLM](https://github.com/BerriAI/litellm) — unified LLM API for 100+ providers

## Inspirations from our greatest of grand parents

The more I study, the more insatiable do I feel my genius for it to be

That brain of mine is something more than merely mortal; as time will show

I believe myself to possess a most singular combination of qualities exactly fitted to make me pre-eminently a discoverer of the hidden realities of nature.

The Analytical Engine has no pretensions whatever to originate anything. It can do whatever we know how to order it to perform.

The intellectual, the moral, the religious seem to me all naturally bound up and interlinked together in one great and harmonious whole.

I have an inexpressible wish to understand what has actually occurred.
