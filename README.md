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

Honest version, as of 2026-09-23.

**What has been proved.** On 2026-09-22 a local model (`qwen3.5:27b`) wrote a
430-line TFTP server that passes **all 31 checks** of a host suite written by a
person, frozen before the run, and never present in the model's workspace.
[The report](.claude/PRPs/reports/w14-f6-qwen-report.md) includes the two defects
in our own harness that nearly buried the result. What made the difference was
not a bigger model but a loop that refuses what it should — non-compiling C never
reaches a reviewer — and a suite honest enough to be wrong out loud.

**What has not.** The memory manager run on 2026-09-23 hit its five-hour timeout
having closed one task of six. Its gates returned `1` (generated wrong) and `2`
(not generated), and
[the report](.claude/PRPs/reports/w15-mm-qwen-report.md) says why.

| | |
|---|---|
| Services generated and passing their gate | **1 of 7** (TFTP). 8 services are specified; `dhcp` already ships in the base, leaving 7 for the swarm |
| Host gate suites | **22**, of which **10** are scored by injected bugs |
| Architectures with a full end-to-end spine | **1** (x86_64); aarch64 boots; riscv64 is specified only |
| CI | 2 workflows, 5 matrix legs — [see below](#continuous-integration) |

There is no finished kernel, and this README will not imply otherwise. What
exists is everything that *judges* a kernel: specifications, gates, oracles,
acceptance harnesses, and an orchestration loop. What remains is running the
swarm — tracked in [`docs/OPEN-WORK.md`](docs/OPEN-WORK.md) and
[`auton-completion.prd.md`](.claude/PRPs/prds/auton-completion.prd.md).

### Why there is no kernel here

`kernels/` is deliberately absent from this repository — it is generated output,
and it is in `.gitignore`. The premise of the project is that agents write the
kernel, so a kernel checked in alongside them would make every gate meaningless.

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
| [`auton-completion.prd.md`](.claude/PRPs/prds/auton-completion.prd.md) | finishing what is defined: every remaining phase with the gate that decides it |
| [`auton-application-to-environment.prd.md`](.claude/PRPs/prds/auton-application-to-environment.prd.md) | new scope: give AUTON an application that already exists and a machine, and derive the minimum environment that runs it |
| [`docs/GENERATION-QUEUE.md`](docs/GENERATION-QUEUE.md) | each generation run, its command, and the gate that decides it |
| [`docs/HOST-MATRIX.md`](docs/HOST-MATRIX.md) | what each host can build, boot and verify — and what it cannot |
| [`agent/kernel_spec/`](agent/kernel_spec/) | the kernel specification the agents are held to |

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
cd AUTON/agent
pip install -e .                          # Python >= 3.11

cp config/auton.toml.example config/auton.toml
export ANTHROPIC_API_KEY="sk-ant-..."     # or OPENAI_API_KEY, or none for Ollama

auton run "Build a bootable kernel with SLM rule engine that detects hardware via PCI scan"
```

`auton` has four commands: `run`, `status`, `tasks`, `agents`.

> **Before spending a run on a local model, qualify it.**
> `scripts/model-probe.py` puts a model through four checks — tool calling,
> file fidelity, a 25k-character prompt, and a second turn. Four earlier runs on
> an unqualified model produced zero working lines. Qualifying first is what
> changed that.

### I want to run the tests

```bash
pytest agent/tests/unit/                          # orchestrator unit tests
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
3. **Developers** (in parallel) implement on feature branches: write → build → fix → test → commit
4. **Reviewer** checks each branch for correctness, memory safety and composition risk
5. **Tester** validates in QEMU — boots the kernel, parses serial output
6. **Integrator** merges approved branches and runs the full suite
7. **Composition Validator** detects the "Frankenstein effect" — subsystems that pass alone and fail together
8. Loop until the tasks complete or the budget is spent

A syntax gate sits in front of step 4: code that does not compile never reaches
a reviewer. It exists because a model reviewer once approved a header with seven
syntax errors in it.

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
  known-good implementation; every one must be caught, or the suite has a gap.
  10 of the 22 host suites are scored this way.
- **Report either way.** Failed runs get a report with the same care as
  successful ones — see the
  [memory-manager report](.claude/PRPs/reports/w15-mm-qwen-report.md).

The gates live in [`tests/kernel/`](tests/kernel/) and run on the host, against
the specification, without the kernel needing to boot.

## Key concepts

### SLM-driven OS
The kernel embeds a Small Language Model as its interface. The SLM is
**pluggable**: a rule-based engine runs on minimal hardware, and systems with
enough resources can load a real neural model.

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
