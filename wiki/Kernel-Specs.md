# Kernel Specs

[`agent/kernel_spec/`](https://github.com/EdWelsh/AUTON/tree/HEAD/agent/kernel_spec) is the
specification the agents are held to. Agents read it with `read_spec <name>` (a whole spec,
or one section). It is input to generation, not a kernel.

## Layout

| Path | What | `read_spec` name |
|---|---|---|
| `architecture.md` | the whole system, subsystem boundaries | `architecture` |
| `subsystems/` | boot, **cpu**, mm, sched, ipc, dev, drivers, fs, net, pkg, sys, slm | `mm`, `cpu`, … |
| `arch/` | x86_64, aarch64, riscv64, and the HAL contract every port implements | `arch/x86_64`, `hal` |
| `drivers/` | driver records: e1000, virtio-net, virtio-blk, framebuffer, PS/2; strategy and licences | `drivers/e1000` |
| `services/` | dhcp, tftp, fileserver, kvstore, smtp, ssh, host-repo, play-doom | `services/smtp` |
| `mitigations/` | F00F IDT remap, FDIV reference check | `mitigations/f00f-idt-remap` |
| `targets/` | target machines (Firecracker, …) so the target is data, not a literal | `targets/firecracker` |
| `decisions/` | owner decisions: Doom licence, fleet endpoint, SSH crypto, first substrate, syscall scope, subject trust | — |
| `conformance/` | silicon conformance checks (FP division, sqrt, single, guaranteed #UD) | — |
| `specialists.yaml` | the 24 specialist agents (see [[Specialists]]) | — |
| `catalogue.yaml` | what AUTON can do, each status citing evidence | — |
| `capability_gates.yaml`, `source_map.yaml` | capability-to-gate and capability-to-source maps | — |
| `reference/`, `templates/` | measured surfaces (e.g. the 49 libc names Doom needs) and per-arch linker scripts | — |

## Front matter

Each subsystem spec starts with what it provides and depends on:

```yaml
---
subsystem: cpu
provides: [cpu-features]
depends_on: []
optional: []
---
```

`capability_slice.py` reads these to compute the minimum set of subsystems an image needs, and
a test fails if a capability has two owners.

## REQUIRED sections

A spec marks what every generated kernel must do with **REQUIRED**, and says how a gate
checks it: the exact boot line (`[MM] PMM initialized: …`), the interface header the frozen
suite compiles against, the edge cases the suite tests. Interfaces that a suite compiles
against are seeded into each run's workspace and are normative where prose and header
disagree.

## The `cpu` subsystem

Added 2026-10-17 ([`subsystems/cpu.md`](https://github.com/EdWelsh/AUTON/blob/HEAD/agent/kernel_spec/subsystems/cpu.md)):
code outside it uses only the architecture's **baseline** instruction set; anything else is
used only behind `cpu_has()`, detected once at boot from CPUID (x86), the ID registers (Arm)
or the ISA string (RISC-V). A vendor string never implies a feature. AVX counts as present
only after `CR4.OSXSAVE` and `XCR0` enable it. The kernel prints one `[CPU]` line the
conformance harness compares with what it measured. See [Hardware Knowledge](Hardware-Knowledge).
