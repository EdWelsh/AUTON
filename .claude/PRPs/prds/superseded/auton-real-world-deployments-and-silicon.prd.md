# AUTON: Real-World Deployments and Silicon-Level Hardware Knowledge

**Status**: **SUPERSEDED** by `auton-intent-to-os-compiler.prd.md`

> This PRD was wrong in two concrete ways. It treated the kernel as a fixed artifact that
> accretes features and planned human work to add them; and it triaged Tier 3 by what each
> feature *sounded* like it needed rather than by reading the tree — claiming Doom was blocked
> on storage, a process model and graphics when it needs none of the three. That contradicts `README.md:11` — *"We don't write the kernel. The agents
> do."* The product is a compiler from intent to a purpose-built OS, not a kernel with a
> roadmap. Carried forward into the successor: the grounding fix, the retrieval-not-generation
> device design, and the scenario list (reframed as compiler inputs).
**Created**: 2026-09-12
**Supersedes nothing.** Consumes the E2E spine, eval, and session harness delivered by
`auton-e2e-train-boot-human-test.prd.md` (all 12 phases complete).

## Problem Statement

AUTON can now be trained, booted, talked to, and scored. What it cannot do is anything a
person would actually ask an operating system for. The eval asks *"what is my ip"*; nobody
boots an OS to be told its IP. They boot it to play a game, host a repo, read their mail, or
stand up a database — and AUTON has no test that ends in a working deployment.

Worse, the one capability the chat OS is built around — knowing what hardware it is running
on and which driver to load — is **four hardcoded PCI entries**, and the model that answers
hardware questions has been measured inventing device ids that are not on the bus.

The cost of not solving it: AUTON's scores go up while its usefulness does not, and the
hardware story cannot scale past the single QEMU NIC it was written against.

## Evidence

**The known defects, all measured this month, all still open:**

- **The model cites hardware that is not there.** Phase 7 round 2, 50 novel turns per rung:
  rule engine 0 phantom device citations, rung-3b fp32 **5**, rung-3c int8 **5**.
  `net list all` → *"Unknown PCI device 10ec:8139"*; `check for exposed APIs` →
  *"Unknown PCI device 1022:2000"*. Neither question contains a device id.
  Root cause is in our own corpus: `SLM/tools/build_corpus.py:37` lists `10ec:8139` and
  `1022:2000` in `UNKNOWN_DEVICES` — ids **not on this bus** — with 14 records each. The model
  learned a deflection template with a real-looking id baked in.
- **Where the rule engine deflects, the model answers wrongly.** Same session: the neural
  rungs answer 23 of 50 novel turns against the rule engine's 16, and **all 9** turns where
  neural answers and rule deflects are wrong (`i need gpu access` → the NIC; `can i run nginx`
  → the kubernetes roadmap; `check everything` → the DHCP lease).
  This qualifies the Phase 3b result: 78% correct-or-honest vs the rule engine's 66% was
  measured on prompts that under-sample real operator register.
- **Rung 3b never met its bar.** 78% correct-or-honest / **22% garbage** against a target of
  ≥70% **and** <10%. Escalating the model 8× (6M → 48M) produced 74%/26% — capacity is not
  the constraint.
- **`kubernetes` surfaces raw `kubectl` stderr** — the same connection error four times with
  timestamps and goroutine detail — and `status` aggregates it, inheriting the same wart.
  Tracked in `RAW_DUMP_KNOWN_GAPS`.
- **The orchestrator dispatches nothing.** Tool-calling measured at 8/8, but `get_assignments()`
  returns empty while `get_ready_tasks()` is non-empty and an idle `developer` agent is
  registered. Root cause not isolated (`e2e-orchestrator-lane.md`).

**The hardware gap:**

- `kernels/x86_64/kernel/slm/slm.c:21-24` — the entire device knowledge base is **4 entries**
  (`8086:100E`, `8086:10D3`, `1AF4:1000`, `1AF4:1001`). Upstream `pci.ids` carries roughly
  **2,400 vendors and 36,000 devices**; USB adds thousands more. AUTON knows 0.01% of the
  space it claims to reason about.
- `kernels/x86_64/kernel/dev/` contains **only `pci.c`**. There is no USB stack, no ACPI
  parser, no SMBIOS/DMI reader, no CPUID surface beyond boot. Device discovery is PCI
  config-space enumeration and nothing else.

**The deployment gap — what the booted kernel actually is:**

- **No process model.** No syscall layer, no ring-3 transition, no ELF loader wired to
  execution. The kernel runs in ring 0 and is the only thing running.
- **No storage.** `dev/` has no block driver; there is no filesystem of any kind.
- **No graphics.** No VGA, framebuffer, or VESA code anywhere in the tree.
- `kernels/x86_64/kernel/slm/roles.c` — **7 `CAP_WORKING` against 16 `CAP_ROADMAP`**. The
  kernel is honest about this; the point is that "play Doom" sits behind all three gaps.
- The **host control plane** is a different story: `backends/{desktop,docker,kubernetes,os,
  server,status}` already launch real applications, containers, and k8s workloads from chat.

## Proposed Solution

Three workstreams, in dependency order.

**A — Fix what we measured.** The defects above are not polish; two of them are *truthfulness*
failures, and one of them (phantom device ids) becomes catastrophic the moment workstream C
scales the device table by four orders of magnitude. A model that invents plausible device ids
against a 4-entry table is a curiosity; against a 36,000-entry table it is indistinguishable
from a working system until someone loads the wrong driver.

**B — Real-world deployment scenarios.** Replace "did it answer correctly?" with "did the
thing actually work?" Each scenario is a goal a person would state in their own words, and
each is graded by an **external probe** — an HTTP 200 from the hosted repo, a message arriving
in a real mailbox, a SQL query returning the row that OAuth just created, a frame rendered by
Doom. Chat answers stop being the artifact; deployments become the artifact.

**C — Silicon-level hardware knowledge.** Device identification becomes **retrieval, not
generation**: the model classifies intent and emits a lookup, and the kernel performs an exact
table lookup against a compiled device database shipped in the flat model format. This is the
architectural answer to the phantom-id defect — it makes hallucinating a device id
*structurally impossible* rather than merely unlikely, and it is the only approach that scales
to the real ID space.

## Key Hypothesis

**A language model should never be the source of a device fact.**

Everything else follows. If the model generates `10ec:8139`, no amount of training reduces the
error rate to zero, because generating plausible hex is exactly what it is good at. If the
model instead emits *"look up the device in slot 00:03.0"* and the kernel answers from a
table, the failure mode changes from "confidently wrong" to "not in the table" — which is
honest, actionable, and exactly the `CAP_ROADMAP` convention the project already uses.

Secondary hypothesis: **most real-world scenarios land on the host control plane, not the
booted kernel** — but fewer than first assumed. Kernel-native Doom was initially triaged as
blocked on storage, a process model, and graphics; on inspection it needs none of them (see
Tier 3). The genuinely long arc is writable storage and ring-3 execution. Triage by reading
the tree, not by the size the feature sounds.

## What We're NOT Building

- **Not** a general-purpose OS. No POSIX, no libc, no shell. AUTON is driven by chat.
- **Not** a Linux driver port. Workstream C ships a device *knowledge* base and driver
  *selection*; writing dozens of drivers is a separate, larger effort.
- **Not** graphics in the kernel this cycle. Doom-on-AUTON is a workstream-B host-plane
  deployment, with kernel-native execution recorded as a later arc.
- **Not** a fix for the orchestrator's scheduler. It is listed as a defect with a diagnostic
  next step; it gates nothing here.
- **Not** retraining the SLM to be a better conversationalist. Workstream A makes it stop
  lying; conversational quality is a separate and possibly unreachable goal at 6M parameters.

## Success Metrics

| Metric | Today | Target |
|---|---|---|
| Phantom device citations, 50 novel turns | 5 (neural) | **0** |
| Eval garbage rate, rung-next | 22% | **<10%** |
| Deployment scenarios passing an external probe | 0 | **≥8 of 15** |
| Device KB entries | 4 | **≥30,000** (PCI) + **≥5,000** (USB) |
| Correct driver selected, held-out real hardware | untested | **≥90%** |
| Device facts sourced from a table, not the model | 0% | **100%** |
| Backends surfacing raw tool stderr | 2 | **0** |

## Users & Context

The operator is a person with a machine and an intention. They do not know or care which half
of AUTON serves them. They say *"I want to play Doom"*, and the system's job is to work out
that this needs an OS image, a package, a display, and a process — then either do it or say
precisely which of those four it cannot do.

The second user is the kernel itself: at boot it must identify every device on the bus and
select drivers without a human. That user needs a table, not a conversation.

## Solution Detail

### Workstream A — Fix the measured defects (MUST)

| # | Defect | Fix |
|---|---|---|
| A1 | Phantom device ids | `UNKNOWN_DEVICES` draws only from ids on the bus; add corpus records teaching that a question with **no** device id gets a clarification, not an unknown-device answer. Retrain, re-score, and require `grounding: PASS` in the session harness. |
| A2 | Wrong answers where rule deflects | Teach declining as a first-class skill for out-of-register input. The corpus has 59 OOD records against 555; raise it, and add the operator registers Phase 7 found (shorthand, compound questions, Linux assumptions). |
| A3 | 22% garbage rate | Consequence of A1+A2, re-measured on the **65-prompt** eval (grown from real sessions), not the original 50. |
| A4 | `kubernetes` raw stderr | One refusal string instead of piping `kubectl` stderr; `status` inherits the fix. Remove both from `RAW_DUMP_KNOWN_GAPS`. |
| A5 | Orchestrator dispatches nothing | Diagnostic only: log ready tasks, their roles, and the agent-pool keys inside `get_assignments()`. Two hypotheses remain — role-string mismatch, or every slot considered busy. |

**A1 is a hard gate on workstream C.** Scaling the device table while the model still invents
ids multiplies the hallucination surface by 9,000×.

### Workstream B — Real-world deployment scenarios (MUST)

Each scenario is stated the way a person would state it, and passes only when an **external
probe** confirms the outcome. Tiers reflect what the scenario requires, not how hard it sounds.

**Tier 1 — host control plane, single capability.** Reachable with today's backends.

| # | The ask | External probe |
|---|---|---|
| B1 | *"host this repo"* | `git clone` the served URL and diff against HEAD; HTTP 200 on the index |
| B2 | *"I want to interact with yedgi.com"* | Browser launched, page title matches, a form field is filled and submitted, screenshot captured |
| B3 | *"I want to play Doom"* | Process running, a rendered frame captured and non-blank, input event accepted |
| B4 | *"the disk is nearly full, sort it out"* | Free space measurably higher; nothing in a protected path deleted |

**Tier 2 — host control plane, multi-step with state.** Needs orchestration across backends.

| # | The ask | External probe |
|---|---|---|
| B5 | *"send an email and receive all my emails"* | Message lands in a real IMAP mailbox; inbound fetch returns it with matching body and attachment |
| B6 | *"I need a database to store user information for a new app with RBAC and OAuth"* | OAuth round-trip completes against a real IdP; a user row exists; a query as a low-privilege role is **refused**; as an admin role it **succeeds** |
| B7 | *"set up a CI runner for this repo"* | Runner registers; a pushed commit triggers a job; job log contains the test summary |
| B8 | *"I need a VPN into my home network"* | Tunnel established; a host only reachable through it answers |
| B9 | *"back up my photos somewhere safe"* | Files restored byte-identical from the backup target; backup is encrypted at rest |
| B10 | *"migrate this app from Docker to Kubernetes"* | Same endpoint answers identically before and after; pod count matches the replica request |
| B11 | *"someone is hammering my web server, stop them"* | Offending source rate-limited or blocked; legitimate traffic still 200s. Defensive only |
| B12 | *"spin up a staging copy of production"* | Staging endpoint answers; its data is a snapshot, and a write to staging does **not** appear in production |

**Tier 3 — requires kernel capability that does not exist.** Recorded to be honest about the
arc, not scheduled here.

| # | The ask | Blocked on |
|---|---|---|
| B13 | *"play Doom on AUTON itself"* | **Far less than first assessed — see below.** ~400 lines, no filesystem, no ring-3, no VESA driver |
| B14 | *"serve this repo from the AUTON kernel"* | The kernel already has a working HTTP server; content ships as a Multiboot2 module. No filesystem needed |
| B15 | *"my laptop won't connect to wifi, fix it"* | Workstream C (device ID) + a wifi driver. The diagnosis half is reachable well before the fix half |

**Correction (2026-09-12).** This tier was first written as "storage → process model →
graphics, all three absent." That was wrong, and the tree says so:

- `arch/x86_64/idt.c` already remaps the **8259 PIC** and runs a ~1 kHz PIT timer, with the
  IDT and ISR stubs in place. A PS/2 keyboard is an IRQ1 handler, not new infrastructure.
- `boot/boot_info.c` already walks the Multiboot2 tag list and handles modules (type 3).
  A **framebuffer tag (type 8)** is one more branch — GRUB then sets the mode and hands over a
  linear framebuffer. **No VESA/VBE driver is required.**
- `grub/grub-neural.cfg` already uses `module2` to ship the model. A WAD is another module.
  **No filesystem is required.**
- `lib/phys.c` already provides `dma_alloc`.

Doom runs in ring 0 as the kernel itself, so **no process model is required either**. The work
is roughly: ~5 lines of Multiboot2 header, ~15 lines of tag parsing, ~100 lines of PS/2
keyboard, a GRUB config line, and doomgeneric's six porting functions — call it **400 lines**.

Tier 3 is therefore reclassified: B13 and B14 are *tractable*, not blocked on absent
subsystems. The genuinely long arc is persistent **writable** storage and a ring-3 process
model, and neither is on the path to these two.

**Grading.** Same three buckets as the chat rubric, lifted to deployments: **worked**
(external probe passes), **honestly refused** (states precisely which capability is missing —
`CAP_ROADMAP` at deployment scale), **failed** (claimed success without the probe passing, or
errored). A scenario that claims success while the probe fails is the deployment-level
equivalent of garbage, and is scored as the worst outcome.

### Workstream C — Silicon-level hardware knowledge (MUST)

**Architecture: retrieval, not generation.**

```
  PCI/USB/ACPI enumeration  →  (vendor:device, class, subsystem, revision)
                                         │
                                         ▼
                            exact lookup in the device table
                              (compiled, shipped in the model file)
                                         │
                        ┌────────────────┴────────────────┐
                        ▼                                 ▼
                   hit: name + driver            miss: "not in the table",
                   + confidence                  with the raw ids echoed
```

The SLM's job is **intent classification and phrasing** — deciding that the user asked a
hardware question and rendering the answer as a sentence. It never emits an id.

| # | Deliverable | Detail |
|---|---|---|
| C1 | Device discovery beyond PCI | USB descriptors, ACPI tables for non-PCI devices, SMBIOS/DMI for board and vendor, CPUID for the processor. `dev/` currently holds `pci.c` alone |
| C2 | Compiled device database | Import `pci.ids` + `usb.ids`; compile to a compact, sorted, binary-searchable table. Target ≥30k PCI + ≥5k USB entries in a few hundred KB — it must fit beside a 6 MB int8 model inside the boot budget |
| C3 | New flat-format section | `devices` section alongside `weights` and `vocab`; `VERSION` bump; the kernel rejects a mismatched version loudly, as it already does |
| C4 | Driver selection | Map device → driver name → availability (`present` / `known but not built` / `unknown`). Mirrors Linux's `MODULE_DEVICE_TABLE` idea without porting drivers |
| C5 | Grounded answers | The hardware answer path reads the table. Session `grounding` must be PASS by construction: the model has no way to name a device the table did not return |
| C6 | Held-out hardware eval | Score driver selection against real device ids the corpus never saw. This is the metric that says whether AUTON understands silicon or memorised four devices |

**Why the table ships inside the model file.** The kernel already loads one Multiboot2 module
and runs it in place. A second artifact means a second module, a second version contract, and
a second way for the two to drift apart. One file, one version, one load path.

## Technical Approach

- **Device table format**: sorted `(vendor, device)` u32 pairs with offsets into a string
  pool; binary search, no allocation, no parsing at boot. The kernel is freestanding — the
  table must be usable as mapped bytes, like the weights already are.
- **Size budget**: int8 model is 5.9 MB and the neural RAM floor is 32 M. A 400 KB device
  table is ~7% of the model and does not move the floor. Verify, do not assume.
- **Corpus changes for A1/A2** must pass the existing contamination guard
  (`SLM/tests/test_corpus_disjoint.py`) against the **65-prompt** eval set.
- **Scenario harness** extends the session harness, which already drives a real VM, captures
  transcripts, and asserts machine-checkable properties. External probes are new: HTTP
  clients, IMAP fetch, SQL queries, framebuffer capture.
- **Security**: B11 is defensive only — rate-limit and block, never counter-attack. B6 touches
  OAuth secrets: they come from the environment, never the corpus, and never a transcript. The
  orchestrator's `_run_shell` shell interpolation (`base_agent.py`) remains an open issue and
  must not be in the path of any scenario that takes untrusted input.

## Implementation Phases

| # | Phase | Deliverable | Depends on | Parallel |
|---|---|---|---|---|
| 1 | Grounding fix | A1: corpus fix, retrain, `grounding: PASS`, 0 phantom citations | — | with 2 |
| 2 | Honest refusal | A2+A3: decline as a skill, garbage <10% on 65 prompts | — | with 1 |
| 3 | Backend honesty | A4: `kubernetes`/`status` refusals; `RAW_DUMP_KNOWN_GAPS` empty | — | with 1, 2 |
| 4 | Scenario harness | External-probe framework, grading, one Tier-1 scenario end to end | — | with 1–3 |
| 5 | Tier 1 scenarios | B1–B4 passing or honestly refusing | 4 | with 6 |
| 6 | Tier 2 scenarios | B5–B12 passing or honestly refusing | 4 | with 5 |
| 7 | Device discovery | C1: USB, ACPI, SMBIOS, CPUID enumeration | — | with 1–6 |
| 8 | Device table | C2+C3: compiled DB, flat-format section, version bump | 7, **1** | — |
| 9 | Grounded hardware answers | C4+C5: driver selection, model never emits an id | 8 | — |
| 10 | Silicon eval | C6: held-out device eval, ≥90% driver selection | 9 | — |
| 11 | Orchestrator diagnosis | A5: one diagnostic, root cause named | — | **do first** |

**Phase 8 depends on Phase 1**, not for convenience but because shipping a 36,000-entry table
to a model that invents device ids makes the defect 9,000× larger.

**Phase 11 is listed last but should be done first.** It is one diagnostic, and it is the
multiplier on everything else in this document. Across the previous PRD's twelve phases, every
line of kernel C was hand-written — **+285/−66** — while the orchestrator that exists to write
kernel code produced a **zero-line diff**. `get_assignments()` returns empty while
`get_ready_tasks()` is non-empty and an idle `developer` agent is registered. If agents are
meant to run continuously, the difference between a working scheduler and a broken one is the
difference between hundreds of hand-written lines and thousands of generated ones. Nothing
else here changes that ratio.

## Open Questions

1. **Does driver selection need the model at all?** If discovery is enumeration and
   identification is a table lookup, the SLM's role in the hardware path may be limited to
   phrasing. That would be a good outcome — and it should be measured, not assumed.
2. **How much of `pci.ids` is worth shipping?** The full table is ~36k devices; a QEMU/laptop
   subset might be 500. Shipping everything is simple and honest; shipping a subset is smaller
   but needs a defensible selection rule.
3. **What does "AUTON hosts this repo" mean when the kernel has no storage?** B14 is
   tantalising — the kernel already has a working HTTP server. Serving from a Multiboot2
   module is possible without a filesystem. Worth a spike.
4. **Can a 6M model learn to decline reliably?** A2 assumes yes. Phase 3b's evidence is that
   capacity was not the constraint, which supports it, but declining is a different skill from
   answering and has not been trained for directly.
5. **Which IdP for B6?** A local Keycloak/Dex is reproducible and offline; a real provider is
   more honest about the integration. Probably local, recorded as a deviation.
6. **Do Tier 2 scenarios need the orchestrator?** B7 and B10 are multi-step. If the
   orchestrator stays blocked (A5), the operator agent may be the only driver available.

## Decisions Log

| Decision | Rationale |
|---|---|
| Device facts come from a table, never the model | A generative model can always produce plausible hex. Measured: 5 phantom citations in 50 turns |
| Device table ships inside the model file | The kernel already loads one module in place; two artifacts means two version contracts that can drift |
| Scenarios graded by external probe, not chat answer | "Did it answer well" is what we already measure and it did not stop 9/9 wrong answers on novel input |
| Tier 3 recorded but not scheduled | Kernel Doom needs storage, a process model, and graphics. Saying so beats a phase that cannot land |
| Phase 1 gates Phase 8 | Scaling the table under an active hallucination defect is the single worst sequencing error available |
| Defensive security only (B11) | Blocking and rate-limiting are operations; counter-attack is not |
| Tier 3 reclassified after reading the tree | Doom was triaged as blocked on three absent subsystems; it needs none of them. PIC, IDT, tag parsing, modules and an allocator all exist |
| Orchestrator diagnosis promoted to first | Every kernel line this cycle was hand-written (+285/−66) while the agent loop produced zero. A working scheduler is the multiplier on all other work |

## Research Summary

- `pci.ids` (The PCI ID Repository) and `usb.ids` are the canonical public device-identity
  sources, maintained continuously and shipped by every Linux distribution. No comparable
  single source exists for driver *mapping* — Linux encodes it per-driver in
  `MODULE_DEVICE_TABLE`, which is the model C4 mirrors.
- Device identity beyond PCI requires ACPI (non-enumerable devices), USB descriptors, SMBIOS
  for board/vendor, and CPUID for the processor. None of these exist in `dev/` today.
- The existing evidence that generation is the wrong mechanism is our own: Phase 7 round 2
  measured the rule engine at **0** phantom citations and both neural rungs at **5**, on
  identical input. The deterministic path is already the accurate one.
