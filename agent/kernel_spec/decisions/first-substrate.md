# Decision (open, owner): the first substrate for application-to-environment

**Status: open.** It blocks A8 (the Packager builds a recipe for *some* substrate) and shapes
A5's sandbox. A1–A4 and A6 are substrate-agnostic. Plans:
[`w20-app-packager`](../../../.claude/PRPs/plans/w20-app-packager.plan.md),
[`w19-app-observe`](../../../.claude/PRPs/plans/w19-app-observe.plan.md).

## Why this is a decision and not a task

The PRD deliberately does not make AUTON's own kernel the target for arbitrary applications: it
has no POSIX, no libc, no shell, by design. The substrates are the ones the control plane
already drives. Which one comes first decides the output format the Packager writes, the cost of
every ablation step (A9 rebuilds once per capability), and what "minimal" can even be measured
against.

## What is already true

- The control plane already runs containers as argv (`controlplane/src/controlplane/backends/docker/client.py`).
- MicroVM targets are already **derived with zero questions** from `agent/kernel_spec/targets/hypervisors.yaml` (D5, hardware-definition PRD).
- `run-intent-probe.sh` grades a QEMU-booted image from outside; the same rubric extends to either substrate.

## Options

| | Container (Docker/OCI) | MicroVM (Firecracker / QEMU `microvm`) |
|---|---|---|
| Build + probe cost per ablation step | seconds, with layer cache | tens of seconds (image build + boot) |
| What "minimal" can measure | userland only: libraries, paths, executables. The kernel is the host's | userland **and** kernel: a guest kernel config is part of the environment |
| Syscall/driver claims | untestable: the host kernel answers them | testable |
| Isolation for A5 observation | namespaces + seccomp; shared host kernel | hardware virtualisation |
| Reuse of AUTON's own work | control-plane docker backend | hypervisor table, target derivation, QEMU probe harness |
| Runs on this Mac | yes (Rancher/Docker Desktop, already a Linux VM) | QEMU TCG only for x86 guests; HVF for arm64 guests |

**Recommended default (not a decision):** container first for A8/A9, because ablation multiplies
the per-step cost by the number of capabilities and the three-application metric needs many
steps; microVM for A5 *observation* if subject-trust says untrusted code must not share a kernel
with the host. A microVM Packager recipe then follows as a second substrate, and nothing
upstream of A8 changes.

## Verdict

*(empty — the owner writes the decision and its reasoning here)*
