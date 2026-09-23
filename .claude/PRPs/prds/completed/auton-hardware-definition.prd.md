# PRD: Hardware Definition and Target Acquisition

**Status**: proposed
**Depends on**: H1 (vendor inventory, landed), H5 (silicon identity, landed), intent-B (manifest, landed)
**Blocks**: driver development (`auton-driver-development.prd.md`) entirely

## Problem Statement

Agents build a kernel for hardware they cannot see.

Today the target is implicit and hardcoded: QEMU's idealised PC, with an e1000 NIC at
`8086:100e` and a serial console at the legacy port. Every driver decision, every device
assumption and every `[DEV] PCI scan: 4 devices found` is written against that one machine.
Nothing asks what the user is actually building for, and nothing records the answer.

That is tolerable while there is one target. It is the binding constraint the moment there are
two.

The user should be able to say *"this is a Dell R740"* or *"this is a Firecracker microVM"* or
*"this runs on the k8s cluster another AUTON image is serving"*, and the agents should build the
right thing — asking only what they cannot determine, and recording what they assumed.

## Evidence

- `agent/kernel_spec/subsystems/dev.md` — the device framework is specified, but every device
  assumption in the shipped corpus and rule engine names the QEMU PC: `SYS_FACTS["devices"]` is
  `8086:1237 8086:7000 1234:1111 8086:100e`.
- `SLM/tools/build_corpus.py` `PCI_KB` — **4 devices**. The ingested `pci.ids` registry knows
  **21,564 across 1,011 vendors** (`.claude/PRPs/reports/w2-hardware-ingestion.md`).
- `agent/kernel_spec/arch/hal.md` category 8 — `arch_cpu_identity()` captures family, model,
  stepping and microcode, with `IDENT_UNKNOWN` distinct from zero. It reads the machine it is
  *running on*, which is the wrong end: a build needs to know the target before it boots there.
- `agent/tools/intent_manifest.py` — turns a sentence into required capabilities, and records
  applied defaults in an `assumptions` list. The same discipline applied to hardware is most of
  this PRD.
- `agent/hardware/CONFORMANCE-HARDWARE.md` — the hardware H10 needs, and what is unobtainable.
  Written for conformance; the target taxonomy below subsumes it.

## What a target actually is

A "hardware spec" is not one thing, and conflating the cases is how a build produces an image
that cannot boot.

| Class | What devices exist | What can be trusted |
|---|---|---|
| **Bare metal** | Whatever the firmware enumerates: real PCI, real errata, real silicon defects | Nothing until probed. Errata apply. This is where `auton-hardware-truth.prd.md` earns its keep |
| **Full VM** (KVM, VMware, Hyper-V) | A hypervisor-chosen set, usually virtio plus emulated legacy | The hypervisor's contract. Errata are the *host's* problem, not the guest's — mostly |
| **microVM** (Firecracker, Cloud Hypervisor) | A deliberately minimal virtio set; often no PCI at all, MMIO instead | A much smaller surface, and the most realistic target for AUTON today |
| **k8s pod** | Whatever the CRI gives a sandboxed VM — in practice a microVM | The runtime class. Only meaningful with a VM-backed runtime |
| **AUTON-hosted** | An AUTON image providing the node another AUTON image runs on | Itself. See *The recursive case* |

### The container case, stated honestly

A user may reasonably say *"put this in a Docker container"*. **A kernel cannot run inside a
container.** A container shares the host's kernel; that is what a container is. The request is
not incoherent, but it means one of two things, and the system must ask which:

1. **A microVM the container runtime schedules** — Kata Containers, Firecracker under
   containerd. This is real, common, and the honest interpretation. AUTON is the guest kernel;
   the container runtime is the scheduler.
2. **An OCI image that ships the ISO as an artifact** — for distribution, not execution. Useful,
   and not what most people mean.

Guessing between these produces either an unbootable image or a useless one. The elicitation in
Phase 2 must surface the distinction rather than resolve it silently — this is the same rule as
intent-B's recorded assumptions, applied where the cost of a wrong default is a build that
cannot run at all.

### The recursive case

*"Hosted on its own version of k8s that another kernel team built and deployed."*

This is the most interesting target and the one that most needs a definition format. An
AUTON-built node is not an unknown: it was built from a manifest, so its device set, its
capability slice and its provenance are all **already recorded**
(`agent/tools/package_image.py` writes `PROVENANCE.json`).

A hardware definition for an AUTON-hosted target should therefore be *derived from the host
image's manifest*, not elicited from a human. That is the one case where the target is
perfectly knowable, and it should be the best-supported path, not an afterthought.

## Proposed Solution

A **hardware definition** — a manifest describing the target — joined to the capability manifest
intent-B already produces.

```yaml
---
target: dell-r740-prod
class: bare-metal            # bare-metal | vm | microvm | k8s-pod | auton-hosted
arch: x86_64
silicon:
  vendor: GenuineIntel
  family: 6
  model: 85                  # Skylake-SP
  stepping: 4
  source: user-stated        # user-stated | probed | derived | assumed
devices:
  - id: "8086:1572"          # X710 10GbE
    source: user-stated
    role: network
  - id: "144d:a808"          # Samsung NVMe
    source: user-stated
    role: storage
firmware: uefi               # uefi | bios | device-tree | none
assumptions:
  - "input: assuming serial console; no framebuffer stated"
provenance:
  stated_by: operator
  stated_at: 2026-09-16T10:00:00Z
---
```

**`source` is per-fact and mandatory.** A device the user named, a device probed from a running
machine, a device derived from a host image's manifest, and a device assumed by default are four
different levels of confidence — and a driver decision made on an assumption must be reversible
when the truth arrives. This is `ident_source_t` from H5, generalised.

## Key Hypothesis

**Most hardware definitions can be derived rather than elicited, and the ones that cannot should
be a short conversation rather than a form.**

- An AUTON-hosted target is fully derivable from the host's `PROVENANCE.json`.
- A microVM target is near-fully derivable from the hypervisor and its machine type.
- A VM target is derivable if the operator can run one probe command.
- Only bare metal genuinely requires elicitation, and even then `lspci -nn` output answers most
  of it.

If this holds, the interactive path is a fallback rather than the main road, and the work is
mostly in derivation and probing. If it does not, the elicitation UX is the product and should
be designed as such.

## What We're NOT Building

- **A hardware database.** `pci.ids` is ingested and has 21,564 devices. We join to it.
- **Automatic discovery of unreachable machines.** If the target cannot be probed and the user
  cannot describe it, the honest output is a refusal, not a guess.
- **A GUI.** Elicitation is a chat, which is what this OS is.
- **Support for every class at once.** microVM first: it is the most derivable, the most common
  deployment shape, and the one with the smallest device surface.

## Honest Capability Boundary

We can determine what devices a target *reports*. We cannot determine what a target *is* when
nobody will tell us and nothing will answer a probe.

Specifically out of reach:
- Devices behind a vendor firmware blob that does not enumerate on any standard bus.
- Hardware whose behaviour differs from what it reports — which is precisely the hardware-truth
  problem, and is handled there rather than here.
- A bare-metal target described only as *"a server"*. That is not a hardware definition, and
  the system must say so rather than defaulting to the QEMU PC, which is how every image would
  silently become an image for a machine nobody owns.

## Success Metrics

| Metric | Today | Target |
|---|---|---|
| Targets expressible | 1 (implicit QEMU PC) | **5 classes**, each with a validated definition |
| Facts carrying a source | 0 | **100%** — every device, every silicon field |
| Definitions derived without asking | 0 | **≥3 of 5 classes** derivable or probe-answerable |
| An underspecified target | silently becomes the QEMU PC | **refused, naming what is missing** |
| AUTON-hosted targets derived from host provenance | n/a | **100%** — the host image already recorded it |

## Implementation Phases

| # | Phase | Status | Deliverable | Depends on |
|---|---|---|---|---|
| D1 | **Definition format** | **complete** — [report](../../reports/w6-target-definition-format-report.md) | `kernel_spec/targets/` format; `source` mandatory per fact; two worked examples of different classes | — |
| D2 | **Derivation — AUTON-hosted** | **complete** — [report](../../reports/w6-target-derivation-auton-hosted-report.md) | A host image's `PROVENANCE.json` yields a complete target definition, no questions asked | D1, intent-F |
| D3 | **Derivation — microVM** | **complete** — [report](../../reports/w6-target-derivation-microvm-report.md) | Hypervisor + machine type yields the virtio device set. Firecracker first | D1 |
| D4 | **Probe ingest** | **complete** — [report](../../reports/w6-target-probe-ingest-report.md) | `lspci -nn`, `/proc/cpuinfo`, `dmidecode` output pasted into chat becomes a definition, joined to `pci.ids` | D1, H2 |
| D5 | **Elicitation** | **complete** — [report](../../reports/w6-target-elicitation-report.md) | The agent asks only what is neither derivable nor probeable, one question at a time, and records every answer with `source: user-stated` | D1–D4 |
| D6 | **Validation and refusal** | **complete** — [report](../../reports/w6-target-validation-refusal-report.md) | A definition that cannot support a bootable image is refused with the missing facts named — never defaulted | D1 |
| D7 | **Join to the capability manifest** | **complete** — [report](../../reports/w6-target-capability-join-report.md) | A target plus an intent yields the device-driven capabilities (`e1000` vs `virtio-net`) automatically | D1, intent-B |
| D8 | **Errata join** | **complete** — [report](../../reports/w6-target-errata-join-report.md) | A defined target's silicon is looked up in the errata table; applicable errata reported before the build, not after | D1, H4, H5 |

## Planning order

All eight phases are tractable now — none is blocked on agents, drivers or real hardware, which
makes this the only PRD in the set that can be finished start to finish today.

**Wave A — the foundation** (built; plans archived in `plans/completed/`)

| Plan | Phase | Why first |
|---|---|---|
| `w6-target-definition-format` | D1 | Everything else reads the format |
| `w6-target-validation-refusal` | D6 | The format and its refusals are one idea; a target that silently becomes the QEMU PC is the defect this PRD exists for |
| `w6-target-derivation-microvm` | D3 | The most derivable class and the smallest device surface. If the key hypothesis holds anywhere it holds here |
| `w6-target-derivation-auton-hosted` | D2 | The recursive case. Also the only one that needs packaging changed first, so it should not be last |

**Wave B — the rest** (D4, D7, D8 planned; D5 deliberately not)

| Plan | Phase | Why in this order |
|---|---|---|
| `w6-target-capability-join` | D7 | D1–D3 built targets nothing reads. `e1000` is hardcoded into three intent rules, so every network image is built for an Intel NIC whatever the machine — this is where a target starts changing what gets built |
| `w6-target-probe-ingest` | D4 | Bare metal is the one class that can be neither derived nor decided. Also the only phase that unblocks another |
| `w6-target-errata-join` | D8 | The smallest remaining phase: every input landed, nothing joins them. The central risk is that assumed silicon reads as a clean bill of health |
| D5 elicitation | — | **Not planned.** Its input is D4's probe output, and the shape of what elicitation must ask is the complement of what probing answers. Planning it now would mean inventing that boundary in a plan file — see `plans/DEFERRED.md` |

D5 is last on purpose. If D2–D4 work, elicitation is a fallback, and building it first would make
a form the product.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Elicitation becomes a 40-question form nobody finishes | **H** | D2–D4 first. Asking is the fallback, and the metric is how rarely it is needed |
| A user describes hardware they do not have | **M** | `source: user-stated` is recorded, and D8's errata join will often contradict a wrong claim before the build |
| The container case is accepted uncritically | **H** | Stated above: a kernel cannot run inside a container. D5 must surface the microVM/artifact distinction, not resolve it |
| Derived definitions drift from the host image | **M** | Derivation reads `PROVENANCE.json`, which carries hashes. A changed host image is detectable |
| "Most secure and optimal" is treated as one axis | **H** | They conflict. The driver PRD makes the trade explicit and refuses to choose silently |

## Open Questions

1. **Is a target definition per-image or per-fleet?** A k8s node pool is many identical machines;
   a bare-metal estate is not. Probably per-fleet with per-machine overrides, but that is a guess.
2. **What happens when the target changes under a built image?** A VM migrated to different
   hardware, a node pool upgraded. The image has baked-in driver decisions.
3. **How much does a microVM need to be told at all?** If the answer is "the machine type and
   nothing else", D3 is most of this PRD and D5 is rarely reached.
4. **Does an AUTON-hosted target inherit the host's errata?** A guest on defective silicon is
   affected by defects the host does not mitigate. H8 answers per-machine; this is per-stack.
