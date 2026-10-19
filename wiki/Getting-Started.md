# Getting Started

Everything here runs from a fresh clone. Python 3.11 or newer.

## Set up

```bash
git clone https://github.com/EdWelsh/AUTON.git
cd AUTON
python3 -m venv .venv && .venv/bin/pip install -e "agent[dev]"
cp agent/config/auton.toml.example agent/config/auton.toml
scripts/preflight.sh                  # tools present, enough free disk
```

Linux needs `build-essential grub-pc-bin xorriso qemu-system-x86` (and `libclang-rt-18-dev`
for the AddressSanitizer host suites); macOS:
`brew install qemu xorriso x86_64-elf-gcc x86_64-elf-binutils i686-elf-grub`.
`scripts/lib/toolchain.sh` resolves per-platform tool names.

## Boot a kernel base

Base trees are tagged starting points (`kernel-base-v5` is the default), materialised into a
directory outside git's index:

```bash
scripts/kernel-base.sh .artifacts/kernels/x86_64
scripts/boot-marker.sh "$PWD/.artifacts/kernels/x86_64" '^\[NET\]'   # build the ISO, boot, wait for a line
```

Docker alternative (no host toolchain): `scripts/kernel-base.sh .artifacts/kernels/x86_64` then
`docker compose run os` (build and boot) or `docker compose run acceptance`.

## Run the tests

```bash
cd agent && ../.venv/bin/python -m pytest tests/unit tests/integration -q    # ~2,200 tests
cd .. && PYTHONPATH=SLM .venv/bin/python -m pytest SLM/tests -q              # SLM pipeline
tests/kernel/run_mm_test.sh --self-test        # a host gate against its reference
tests/kernel/run_mm_test.sh --inject           # the suite scored by injected bugs (9/9)
```

## Run a swarm

Every swarm writes into a testing area, and every run spends model calls: qualify the model
first, start one small run, read it, then continue.

```bash
.venv/bin/python scripts/model-probe.py claude-cli/claude-sonnet-5-5     # 4 checks
.venv/bin/python scripts/campaign.py --only r1-mm                         # kernel: one run
.venv/bin/python scripts/slm_run.py start chat-1 --goal "Train the kernel chat model"
.venv/bin/python scripts/vendor_research.py start scout-1 --goal "Document the top 5 uncovered CPU vendors"
```

Models: any LiteLLM provider with its API key, a local Ollama model, or the Claude
subscription through Claude Code (`claude-cli/<model>`, no key). See [[Configuration]].

## Ask the hardware tables

```bash
python agent/tools/vendor_registry.py --lookup 8086          # who is this vendor?
python agent/tools/isa_tables.py --has alderlake avx512f     # check at runtime: fused-off
python agent/tools/isa_tables.py --cpuid fma4                # leaf 0x80000001 ECX bit 16
python agent/tools/qemu_cpu.py qemu64                        # the CPU every gate boots on
```
