# PRD: Driver Selection, Synthesis and Provenance

**Status**: proposed
**Depends on**: hardware definition (`auton-hardware-definition.prd.md`) entirely; F5 (factory
pipeline, landed); H6 (mitigation registry, landed)
**Blocks**: intent-G (Doom — needs framebuffer + input), F7–F11 (storage and the service ladder)

## Problem Statement

`agent/kernel_spec/subsystems/drivers.md` specifies five SLM-managed drivers: AHCI, NVMe,
VirtIO Block, e1000 and VESA framebuffer. **Two were ever implemented** — e1000 and the 16550
serial console; the timer came in through `arch/idt.c` rather than a driver.

The capability index advertises nine driver capabilities. Three resolve to code that existed
(`serial`, `timer`, `e1000`). **Six do not**, and they fail in two different ways:

- `framebuffer` → `kernel/drivers/fb/**` and `virtio-blk` → `kernel/drivers/blk/**` map to
  directories that have never existed.
- `keyboard` and `input` map to `kernel/drivers/arch/**`, which existed and contained only the
  serial console.
- `ahci` and `nvme` have **no source mapping at all** — `build_manifest.py` reports them as
  unmapped capabilities, so an image requiring one silently omits it.

The last is the worst of the three: a manifest can require `nvme`, resolve to a closed slice,
pass every spec-stage gate, and produce an image with no storage driver in it.

Meanwhile the ingested `pci.ids` registry knows **21,564 devices**. The gap between "devices
the world has" and "devices AUTON can drive" is four orders of magnitude, and every intent that
needs storage or a display is blocked behind it. Doom needs a framebuffer and an input device.
Neither exists.

So: given a hardware definition, the agents must decide **per device** whether to reuse an
existing driver, port one, or write one — and then build, install and verify it.

The user's framing was *"whichever is more optimal and secure"*. Those are two axes and they
conflict. Making the trade explicit is most of this document.

## Evidence

- `drivers.md:50,113,163,216,279` — AHCI, NVMe, VirtIO Block, e1000, VESA specified.
- `capability_slice.py` → `drivers` provides `serial, timer, keyboard, framebuffer, e1000,
  virtio-blk, ahci, nvme, input`. `source_map.yaml` maps `framebuffer` to
  `kernel/drivers/fb/**` and `virtio-blk` to `kernel/drivers/blk/**` — **neither directory has
  ever existed**.
- `.claude/PRPs/reports/w2-hardware-ingestion.md` — 21,564 PCI devices, 1,011 vendors, with
  provenance. AUTON's own knowledge base has 4.
- `.claude/PRPs/reports/w4-intent-packaging.md` — the Doom package is `INCOMPLETE`. The blocker
  it *names* is the missing service spec, because that is the nearer wall; the reason that spec
  has not been written is that nothing could implement it — there is no framebuffer and no input
  driver.
- `.claude/PRPs/reports/w3-factory-dhcp-service.md` — a service was authored by hand in 401
  lines against a spec, with 24 host tests. That is the cost baseline a *driver* should be
  measured against.
- `agent/kernel_spec/mitigations/README.md` — the rule that a mitigation must state its cost and
  how to verify it. A driver needs the same, for stronger reasons.

## The security argument, stated first

A driver is the most dangerous code in the image.

It runs in ring 0. It programs DMA, which means it can write any physical address regardless of
page tables. It parses data produced by a device that may be malicious, malfunctioning, or
mercurial. There is no process boundary to contain it — AUTON has no process model, which is
the same property that makes the unikernel small.

So "optimal" and "secure" are not aligned:

| Option | Optimal for | Costs |
|---|---|---|
| **Reuse** a vetted driver | Correctness, time | Licence constraints; the driver may assume a kernel AUTON is not |
| **Port** from an open driver | Correctness, coverage | Porting bugs are subtle and land in ring 0; the source's assumptions come with it |
| **Synthesize** from a vendor spec | Minimality, exact fit, no inherited assumptions | **Nobody has ever run this code.** A synthesized DMA programming error is an arbitrary-write primitive |

The honest default is therefore **reuse > port > synthesize**, and synthesis must carry the
heaviest verification burden rather than the lightest. A generated driver that boots is not a
verified driver; it is a driver that has not failed yet.

## Proposed Solution

A **driver decision record** per device in the target definition, and a pipeline that produces
one of three outcomes with its evidence.

```yaml
---
device: "8086:1572"                  # Intel X710 10GbE
identified_as: "Intel Corporation Ethernet Controller X710"
identified_from: pci-ids@2026.09.15  # provenance, per H2's rule
decision: port
rationale: >-
  No in-tree driver. The device is documented in Intel's X710 datasheet
  (public-download), and an open driver exists whose licence permits porting.
  Synthesis was rejected: the descriptor ring format is intricate and a DMA
  error here is an arbitrary write.
source: "intel/i40e, GPL-2.0"
capabilities_needed: [dma, mmio, msi-x]
verification:
  - link comes up and reports the negotiated speed
  - a frame sent is received by a second host
  - the descriptor ring is bounded: a malformed descriptor is rejected, not followed
review: required          # required | waived-with-reason
status: proposed          # proposed | implemented | verified | rejected
---
```

**`verification` is mandatory and must be executable.** This is H6's rule for mitigations,
applied where the stakes are higher: an unverified driver claim is worse than no driver,
because the image boots and appears to work.

## Key Hypothesis

**Driver selection is a retrieval problem, not an inference problem.**

This session measured the same claim in a different domain and it held: moving device and system
answers from the model to a deterministic table took the chat's garbage rate from 23.1% to 12.3%,
where growing the training corpus by 68% had moved it only to 21.5%
(`.claude/PRPs/reports/w5-over-refusal-fix.md`).

The same logic applies here, and more strongly. `8086:1572` **is** an X710 — that is a table
lookup against an ingested registry with provenance, not a judgement. Which driver strategy suits
it is a decision over a small, enumerable set of options with stated criteria. Neither step wants
a model inventing a plausible answer, and a model that invents a driver for a device that is not
present is the phantom-PCI-id defect with a DMA engine attached.

The model's job is the prose: reading a vendor datasheet and drafting an implementation against
it. The decision of *whether* to draft is a table.

## What We're NOT Building

- **A driver for every device.** 21,564 is not a target. The target is the devices real
  deployments have, which the hardware-definition work will enumerate.
- **A general-purpose DMA API.** Drivers get the allocator F3 specifies and nothing more.
- **Binary blob loading.** A driver AUTON cannot read is a driver AUTON cannot verify.
- **Hot-plug.** `dev.md` specifies it; it is not needed for any image this PRD unblocks.
- **Synthesis as the default.** It is the last resort, and the one that must prove itself.

## Honest Capability Boundary

We can identify a device, select a strategy, and verify a driver against behaviour we can
provoke. We cannot verify a driver against behaviour we cannot provoke.

Specifically:
- **Under emulation, a driver is verified against QEMU's model of the device, not the device.**
  This is exactly the gap `agent/hardware/CONFORMANCE-HARDWARE.md` records for conformance, and
  it applies with full force to drivers. A virtio driver verified under QEMU is verified against
  virtio; an X710 driver verified under QEMU is verified against nothing.
- **A synthesized driver's correctness argument rests on a vendor document** that may itself be
  wrong — which is the premise of `auton-hardware-truth.prd.md`. When a driver and an erratum
  disagree, that is a finding, and it goes through H11's disclosure path.
- **We cannot prove the absence of a DMA bug by testing.** The verification list bounds the
  risk; it does not eliminate it. A driver written by an agent and reviewed by nobody should not
  ship, and `review: required` is the default for that reason.

## Success Metrics

| Metric | Today | Target |
|---|---|---|
| Drivers specified | 5 | 5 |
| Drivers implemented | **2** (serial, e1000) | **6** — add virtio-net, virtio-blk, framebuffer, input |
| Capabilities advertised with no implementation | **6 of 9** | **0** — advertise nothing that does not exist |
| Driver decisions with a recorded rationale | n/a | **100%** |
| Drivers shipped without executable verification | n/a | **0** |
| Synthesized drivers shipped without human review | n/a | **0** |
| Intents unblocked | 0 | **Doom** (framebuffer + input), **storage** (virtio-blk) |

## Implementation Phases

| # | Phase | Deliverable | Depends on |
|---|---|---|---|
| V1 | **Truth up the capability index** — **complete**, [report](../reports/w6-driver-capability-honesty-report.md) | **27** capabilities across **11** subsystems have no source mapping, not the two first reported. Most of that is correct per-tree information; the defect is that nothing acts on it — `resolve()` computes the list, `main()` warns to stderr, and the pipeline never reads it. Make it load-bearing | — |
| V2 | **Decision record format** — **complete**, [report](../reports/w6-driver-decision-record-report.md) | `kernel_spec/drivers/` per-device records; `verification` mandatory and executable; two worked examples of different strategies | D1 |
| V3 | **Identification from the registry** — **complete**, same report | A device id yields its identity from ingested `pci.ids` with provenance — deterministic, no model | H2 |
| V4 | **Strategy selection** — **complete**, [report](../reports/w7-driver-strategy-selection-report.md) | reuse / port / synthesize, from stated criteria, with the rationale recorded. Refuses rather than guessing when no option is defensible | V2, V3 |
| V5 | **virtio-net, human-authored** — **complete**, [report](../reports/w7-driver-virtio-net-report.md) | The control, as DHCP was for services. virtio because microVMs need it and its spec is open | V2, F5 |
| V6 | **virtio-blk** — **complete**, [report](../reports/w8-driver-virtio-blk-report.md) | Unblocks storage, and with it the whole service ladder F7–F11 | V5 |
| V7 | **Framebuffer + input** — **complete**, [report](../reports/w8-driver-framebuffer-input-report.md) | Unblocks Doom, which is the PRD-set's headline intent and currently `INCOMPLETE` | V5 |
| V8 | **Agent-authored driver** — **re-run w13 on the repaired loop: one invalid record, no reference or tests**, [report](../reports/w13-driver-v8-rerun-report.md); gate suite frozen (29 checks, 8/8 injected bugs); awaits a capable model (owner). w11: **run once, produced nothing**, [report](../reports/w11-driver-agent-authored-report.md). Loop defects, not the model: empty-diff review + terminal rejection. Re-run after the loop fix — *planned: [`w13-driver-v8-rerun`](../plans/completed/w13-driver-v8-rerun.plan.md)* | The real test: the loop drafts a driver from a vendor spec, a human reviews, cost measured against V5. Requires the F6 workspace fix | V5, F6 |
| V9 | **Verification harness** — **complete**, [report](../reports/w7-driver-verification-gate-report.md) | Driver verification runs in the factory pipeline as a gate, like leakage | V2, F5 |
| V10 | **Errata join** — *deferred: no document links a device to an erratum* — *planned: [`w13-driver-errata-join`](../plans/completed/w13-driver-errata-join.plan.md)* | A driver for silicon with applicable errata reports them, and applies a mitigation where H6 has one | H4, H6 |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| A synthesized driver has a DMA bug | **H** | Synthesis is last resort; `review: required` by default; verification includes bounds on descriptor handling |
| Verified under QEMU, broken on hardware | **H** | Stated in the capability boundary. Real-hardware verification is gated on the same acquisition `CONFORMANCE-HARDWARE.md` describes |
| "Optimal and secure" resolved silently | **H** | V4 refuses when no option is defensible, and the rationale is a required field |
| Licence contamination from porting | **M** | `source` records the licence; a port from GPL source makes the image GPL, and that must be a stated decision |
| Six advertised-but-absent capabilities keep shipping | **M** | V1 is first for exactly this reason: advertising what does not exist is the same defect as a phantom PCI id |
| Driver count becomes the metric | **M** | The metric is intents unblocked. Two drivers that unblock Doom beat ten that unblock nothing |

## Open Questions

1. **What licence does a ported driver impose on the image?** A GPL port makes the image GPL.
   That is a product decision, not an engineering one, and it should be made before V5 rather
   than discovered at V8.
2. **Can a driver be verified without the device?** Partially — descriptor handling, bounds,
   state machines. Not link-up or throughput. How much of the verification list is reachable
   under emulation decides how much V9 is worth.
3. **Is synthesis ever the right answer?** Possibly for a simple, fully-specified device where
   no open driver exists. If the answer turns out to be "no", V4 collapses to reuse-or-port and
   the PRD gets smaller, which would be a good outcome.
4. **Where does a driver's erratum live?** A device erratum is not a CPU erratum, and H4's table
   is keyed on family/model/stepping. Device errata need their own key — probably
   `vendor:device:revision`.
5. **Do AUTON-hosted targets need drivers at all?** If the host presents virtio, a guest needs
   only virtio, and the whole 21,564-device problem collapses to about four drivers. That would
   make the recursive case not just elegant but the strategically correct default.
