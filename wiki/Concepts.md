# Concepts

## The OS is the chat

An AUTON kernel boots to an `auton>` prompt on the serial console. There is no shell and no
process model. You ask: `what is my ip`, `what can you do`, `be a web server`. Networking comes
up at boot (DHCP over an in-kernel IPv4 stack); roles marked *ready* run on the in-kernel
TCP/IP stack, and *roadmap* roles say what they still need instead of pretending.

The chat routes deterministic handlers first (system queries, server roles, PCI ids) and falls
back to the **SLM**, a small language model running inside the kernel. See [The SLM](SLM).

## Agents write the kernel

The premise, from [NVIDIA VibeTensor](https://github.com/NVlabs/vibetensor): LLM agents can
write system software if the loop around them is honest. AUTON's agents (a manager, an
architect, developers, specialists, a reviewer, a tester and an integrator) work on git
branches in a workspace and merge what passes. See [Agents and Swarms](Agents-and-Swarms).

**This repository holds the agents, not kernels.** A generated kernel lives in a testing area
(`.artifacts/campaign/<run>-attempt<k>/ws`, gitignored). The only kernel C code that is
tracked is in `tests/kernel/`: frozen suites and the hand-written references they are scored
against. A kernel checked in beside the agents would make every gate meaningless.

## Gates decide, not agents

Every run is judged by gates written and frozen **before** it starts:

- exit **0** pass, **1** generated wrong, **2** not generated. A suite that did not run found
  nothing, and must never read as a pass;
- suites are scored by **injected bugs** (`run_mm_test.sh --inject` scores 9/9): a suite that
  cannot fail is not evidence;
- a run is **pre-registered**: its goal, gates and stop rule are committed first, and a
  changed harness is a different experiment.

See [Gates and Testing](Gates-and-Testing).

## The Frankenstein effect

*"Locally correct subsystems interact to yield globally suboptimal performance."* Subsystems
that pass alone can fail together, so integration is checked, not assumed.

## A fact needs a source

- Hardware facts cite a document, revision and page, or they are not added. Fetched vendor
  documents stay in `.cache/vendor/`; only derived records are committed.
- **A document never proves an instruction is present.** Intel specified FMA4 and never
  shipped it; AMD dropped FMA4 in Zen; Alder Lake fused AVX-512 off; microcode turned TSX off.
  The kernel uses anything beyond the baseline only after the running CPU says it has it.
  See [Hardware Knowledge](Hardware-Knowledge).
- **Training answers are generated from ground truth, never written.** See
  [SLM Training Data](SLM-Training-Data).
