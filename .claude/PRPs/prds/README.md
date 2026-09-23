# PRDs

**Repo intent, in one line:** AUTON is an agent team that generates a purpose-built operating
system from a stated need. `README.md:11` — *"We don't write the kernel. The agents do."*

Everything below is aligned to that. If a PRD contradicts it, the PRD is wrong.

## Current state of the repo, which all of these assume

| Fact | Consequence for planning |
|---|---|
| `kernels/` is **gitignored** — no tracked kernel tree | A missing tree is a generation target, not a gap to fill by hand |
| Reference tree is tag **`kernel-reference-v1`** | `git checkout kernel-reference-v1 -- kernels/` restores it; the spine then passes 10/10 |
| Its structure is in `agent/kernel_spec/reference/x86_64/` | 160 functions, 308 call edges, spec→implementation training pairs |
| Its contracts are in `agent/kernel_spec/` | Prompt contract, module validation, degenerate guard, format versioning, retrieval-only device ID |
| Kernel tests live in `tests/kernel/`, not in the kernel tree | Verification must not live inside the artifact it verifies |
| `scripts/e2e.sh --target <dir>` | The spine validates generated output, not a fixed path |
| The agent loop **dispatches zero tasks** | Gates every generation phase in every PRD below |

## Two orderings

**[Read in this order](#read-in-this-order)** to understand the system.
**[Plan in this order](#planning-order)** to build it. They differ: the factory reads first
because everything else depends on its framing, but the first thing to *plan* is a one-line
scheduler fix that appears in no PRD's phase table.

## Read in this order

**1. [`auton-service-kernel-factory.prd.md`](./auton-service-kernel-factory.prd.md)** —
*canonical for generation.* One service spec in, one minimal bootable image out. Contains the
observation the rest depends on: AUTON is already a unikernel, so per-image scoping adds no
architectural debt. 12 phases, a six-service ladder, and the storage unlock.

**2. [`auton-intent-to-os-compiler.prd.md`](./auton-intent-to-os-compiler.prd.md)** — the
layer above. Turns a sentence (`AUTON train "I want to play Doom" --output ./Doom`) into the
spec the factory consumes, scopes the SLM to that intent, and packages an installer. Also
carries the device-table design and the consumer scenario ladder.

**3. [`auton-hardware-truth.prd.md`](./auton-hardware-truth.prd.md)** — what the generated OS
knows about the silicon it runs on. Ingests every public vendor specification and errata
document, keys them to exact silicon identity, generates mitigations for the faults that
apply, and — because every generated image carries an intent-scoped conformance suite — tests
whether a chip honours its own datasheet at install time, on every deployment. That last part
is the FDIV method: both canonical Pentium defects were found by comparing silicon to spec, and
fleet-scale differential testing is how mercurial cores were found more recently. Extends the
intent PRD's device table into an errata table. Absorbs the shell-injection fix deferred by
the orchestrator lane.

**4. [`auton-windows-linux.prd.md`](./auton-windows-linux.prd.md)** — portability. Off one
Mac, onto real hardware and other architectures. Orthogonal to 1 and 2; its
"architectures have no source tree" premise is now answered by generation. Note that (3)'s
conformance harness **requires** this work — QEMU implements an idealised CPU and will not
reproduce silicon divergence.

## Historical — do not plan from these

**[`completed/auton-e2e-train-boot-human-test.prd.md`](./completed/auton-e2e-train-boot-human-test.prd.md)** —
**complete**, all 12 phases. Built the spine, the graded eval, the session harness and the
training pipeline, all of which still stand. Its kernel work was hand-written, which
contradicted the premise; those capabilities are now spec.

**`auton-real-world-deployments-and-silicon.prd.md`** (removed, not archived) —
**superseded**. Planned features for one general kernel, and mis-triaged its own scenarios by
what they sounded like rather than by reading the tree. Its grounding fix, device-table design
and scenario list were carried into (2).

## Planning order

Reading order and planning order are not the same thing. The list above is how to *understand*
the system; this is what to `/prp-plan` and when. Phases interleave across PRDs, so the waves
below name phases, not whole documents.

### Wave 0 — unblock. Nothing else is worth planning first.

| Do | From | Why first |
|---|---|---|
| **Scheduler fix** | (not a PRD phase — one diagnostic) | `get_assignments()` returns empty while a ready task and an idle `developer` agent both exist. Until this works, every generation phase in every PRD is a human writing code — the exact thing this repo exists to avoid |
| **H0 — shell hardening** | hardware-truth | `base_agent.py` interpolates tool arguments into `create_subprocess_shell`. Agents are about to generate far more code, and hardware-truth will point them at externally fetched vendor documents. Fix before either |

Both are small. Neither is optional, and the scheduler fix changes the cost of everything
downstream by an order of magnitude.

### Wave 1 — cheap, parallel, high-information. No cross-PRD dependencies.

| Do | From | Why here |
|---|---|---|
| **D — scoped SLM corpus** | intent | **The single cheapest test of a load-bearing hypothesis.** If intent-scoping fixes the 22% garbage rate for free, a large amount of later modelling work disappears. If it does not, the SLM problem is deeper than generality and that changes the plan |
| **A — capability index** | intent | `provides`/`depends_on` front-matter on the subsystem specs. Everything in the intent PRD rests on it, and it is spec work needing no agents |
| **F2 — service-spec format** | factory | The format intent-C must emit. Blocks the handoff between the two PRDs |
| **F3 — real PMM** | factory | A bitmap allocator behind a `[MM]` marker that finally means something. No dependencies, unblocks storage later |
| **H1 — vendor inventory** | hardware-truth | Pure research: which vendors publish what, under which licence, at what cadence. Unblocks all ingestion |
| **H5 — silicon identity at boot** | hardware-truth | Small, and every errata and conformance phase keys on it |

### Wave 2 — build on wave 1.

| Do | From |
|---|---|
| **F1 — dependency audit + manifest** | factory — now much cheaper: `agent/kernel_spec/reference/x86_64/graph.json` already records the real coupling of the retired tree |
| **B — intent to manifest** | intent (needs A) |
| **H2, H3 — Intel/AMD, then Arm/RISC-V ingestion** | hardware-truth (needs H0, H1) |
| **Start portability** | windows-linux — a long-lead item. Hardware-truth's conformance work **requires** real hardware, so begin it well before you need it |

### Wave 3 — prove the factory by hand before asking agents to do it.

| Do | From | Why this order |
|---|---|---|
| **F4 — service #1, DHCP, human-authored** | factory | Proves the machinery against the spec with a human in the loop. Asking agents to generate a service the process has never produced manually conflates two failure modes |
| **F5 — factory pipeline + gates** | factory | `auton build-service`, the three validators wired to `--target` |
| **C — manifest to service spec** | intent (needs B, F2) | The handoff |
| **H4 — errata table format** | hardware-truth (needs H2) |

### Wave 4 — generation proper. This is where the premise gets tested.

| Do | From | Why |
|---|---|---|
| **F6 — service #2, agent-authored** | factory | **The real test of `README.md:11`.** The loop drafts a service from spec, a human reviews, and the cost is measured against F4's human-authored equivalent. Requires the wave-0 scheduler fix |
| **E — leakage enforcement** | intent (needs C, F5) | Excluded subsystems fail the build. Without it "minimal" is unfalsifiable |
| **F — packaging** | intent | ISO, installer, scoped model, spec subset, provenance |
| **H6, H7 — mitigation registry and generated mitigations** | hardware-truth | F00F-class IDT remap as the worked example |

### Wave 5 — things a user can actually run.

| Do | From |
|---|---|
| **G — I1 Doom** | intent. Needs no network, so it tests `excludes` in one direction |
| **H — I2 host this repo** | intent. Needs no storage, testing `excludes` in the other |
| **H8 — "is this machine safe?"** | hardware-truth |
| **F7–F11 — storage unlock and the service ladder** | factory |

### Wave 6 — hardware reality and the headline capability.

| Do | From | Note |
|---|---|---|
| **Finish portability** | windows-linux | Real hardware, multiple steppings. QEMU implements an idealised CPU and will not reproduce silicon divergence |
| **H10, H10a–e — conformance** | hardware-truth | Semantic (FDIV class) and fault (F00F class) conformance, generated into every image, verified at install, aggregated across the fleet |
| **H11 — disclosure pipeline** | hardware-truth | Must exist before the harness can find anything |
| **I, J — device table, real silicon** | intent |
| **H12, H13 — unmitigated sweep, table merge** | hardware-truth |

### Completed

`completed/auton-e2e-train-boot-human-test.prd.md` — all 12 phases. Its harness and rubric are
still the measurement apparatus everything else uses; two of its recorded *numbers* were
superseded by later work, and the file says which.

### New: hardware definition and driver development

Two PRDs added after waves 0–4, because the blocker analysis kept returning the same answer:
**there are no drivers**, and nothing knows what hardware it is building for.

| PRD | Answers | Blocks |
|---|---|---|
| [completed/auton-hardware-definition.prd.md](completed/auton-hardware-definition.prd.md) — **complete, all 8 phases** | *What am I building for?* Five target classes — bare metal, VM, microVM, k8s pod, AUTON-hosted — with every fact carrying a `source` | nothing; it unblocked the driver PRD entirely |
| [auton-driver-development.prd.md](auton-driver-development.prd.md) | *What drives it?* reuse / port / synthesize per device, with mandatory executable verification | Doom, storage, the whole service ladder |

Read them in that order; the second is meaningless without the first.

**Three things they settle that were previously assumed**

1. **A kernel cannot run inside a container.** The request means a microVM a container runtime
   schedules (Kata, Firecracker) or an OCI image shipping the ISO as an artifact. The
   elicitation surfaces the distinction rather than guessing, because a wrong default here
   produces an image that cannot run at all.
2. **"Optimal and secure" are two axes that conflict.** A driver is ring-0 DMA-capable code with
   no process boundary. Reuse > port > synthesize is the honest default, and synthesis carries
   the heaviest verification burden rather than the lightest.
3. **`nvme` and `ahci` are advertised with no source mapping at all.** A manifest requiring
   either resolves to a closed slice, passes every gate, and produces an image with no storage
   driver. Verified, and V1 of the driver PRD exists for it.

**The recursive case is the strategically interesting one.** An AUTON-hosted target is fully
derivable from the host image's `PROVENANCE.json` — no elicitation needed. And if the host
presents virtio, the guest needs about four drivers rather than 21,564. That may make the
recursive deployment not merely elegant but the correct default.

### Status 2026-09-23: all 90 plans closed; what is left is runs and decisions

**Every PRP plan is in `plans/completed/`.** The work they designed is built and tested. What
remains is not design, so it lives in the repository rather than here:

- **`docs/OPEN-WORK.md`** — every unfinished piece, its blocker (run / decide / hardware) and
  its next step.
- **`docs/GENERATION-QUEUE.md`** — the generation runs, each one command, with the gate that
  decides it and how to qualify a model first.

The headline that changed the shape of what is left: on 2026-09-22 an agent
(`qwen3.5:27b`, qualified 4/4 by `scripts/model-probe.py`) wrote a 430-line TFTP server that
passes **all 31 checks** of a gate suite frozen before the run and absent from its workspace.
Two harness defects had hidden it — the gate's stub shadowed libk so no conformant server could
compile, and the engine orphaned uncommitted work — both now fixed with tests that fail without
them. Generation is no longer the open question; turns, time and a push are.

### Status after w14/w15 host-side work (2026-09-22)

Everything that does not need a capable model or the owner's hardware is built and gated.
What remains is in one of three buckets, and no work is silently blocked:

**Done and proved on the host** (each with a frozen suite, injected-bug scores, and CI wiring):

| Phase | What landed | Suite |
|---|---|---|
| F8 file server | retargeted to the FAT32 disk (was a CPIO boot module) | 29 checks, 8/8 bugs |
| F9 KV store | `kvstore.md`, RESP2 subset, CRC'd log, torn-record recovery | 31 checks, 9/9 |
| F11 email | `smtp.md`, receive + store, sequence recovered by scan | 32 checks, 9/9 |
| F12 SSH | crypto gate **GO** (Monocypher + BearSSL), `ssh.md` | 28 checks, 8/8 |
| F12 catalogue | `catalogue.yaml` + `gen_roles.py`, citations must be tracked files | 14 tests |
| I2 host-repo | dumb-HTTP git layout, graded by a real `git clone` | 28 checks, 7/7 |
| H10 conformance | SoftFloat oracle pinned + self-tested, 28 clause-cited entries | 23/23 match |
| H10c selection | per-image, by disassembly; found and closed the DIVSS/SQRTSS gap | 9 tests |
| H10e fleet | allowlist schema, local aggregator, **no endpoint** | 18 tests |
| D2 aarch64 | DTB parser against real QEMU trees; `ARCH=aarch64` toolchain | 21 checks, 9/9 |
| C1 control plane | Linux green in a container; 3 host bugs fixed; 3-OS CI matrix | 189/178 passed |
| H12 sweep | 51 of 94 ADL errata documented-unmitigated, method stated | 9 tests |

**Waiting on a capable model** (specs, gates and pre-registrations are ready; each run is one
command): `w13-generate-mm`, `w13-generate-storage`, `w13-driver-v8-rerun`, `w14-hardware-h7-run`,
`w14-intent-doom-boots` (also licence-gated), `w15-hardware-conformance-every-image` (runtime half).
Four gemma4 runs produced nothing; `scripts/model-probe.py` now qualifies a model before a run
is spent on it, and `ollama_chat/qwen3.5:27b` is the first to pass all four checks.

**Waiting on the owner**: the gates table below, plus the Intel NIC and per-generation spec-update
PDFs (`w13-driver-errata-join`, `w13-hardware-errata-lineage` — Intel's CDN refuses scripted
downloads), and a `git push` (the branch has never reached CI).

### Status after w11: every remaining phase is planned, start here

32 plans cover every open phase of the five PRDs, plus the three cross-PRD blockers
[ELIGIBILITY.md](ELIGIBILITY.md) identified. Execute with `/prp-implement` **in wave order**.
Within a wave, plans are independent unless a row says otherwise.

| Wave | Plans | Unblocks |
|---|---|---|
| **w12: unblock, no agent loop needed** | `w12-loop-review-repair` (**first**), `w12-kernel-base`, `w12-vmm-spec`, `w12-factory-storage-fat32-spec`, `w12-portability-linux-bench`, `w12-portability-uefi`, `w12-portability-hal-extraction` | all generation; F7; A1/B1/B3/D1 |
| **w13: generation + data** | `w13-factory-f6-rerun` (defines the **Generation Experiment Protocol** every later generation plan cites), `w13-generate-mm` (= windows-linux B2), `w13-generate-storage`, `w13-driver-v8-rerun`, `w13-driver-errata-join`, `w13-hardware-errata-lineage`, `w13-hardware-unmitigated-sweep`, `w13-hardware-table-merge`, `w13-portability-controlplane-hosts` | services, H7, Doom |
| **w14: services and headline intents** | `w14-factory-fileserver`, `w14-factory-kvstore`, `w14-factory-ssh-gate`, `w14-intent-host-repo`, `w14-intent-doom-boots`, `w14-hardware-h7-run`, `w14-hardware-conformance-harness`, `w14-portability-aarch64` | F11/F12, H10c-e |
| **w15: the long tail** | `w15-factory-email`, `w15-factory-catalogue`, `w15-intent-real-silicon`, `w15-hardware-conformance-every-image`, `w15-portability-proxmox`, `w15-portability-wsl2` | metal, fleet |
| **w16: hardware-bound** | `w16-portability-metal`, `w16-hardware-fleet-reporting` | PRD completion |

**Gates only the owner can open.** Each is written into its plan as a precondition, not guessed:

| Gate | Plan | What is needed |
|---|---|---|
| doomgeneric (GPL-2.0) licence | `w14-intent-doom-boots` Task 1 | distribute with GPL obligations / local-only / cut Doom |
| SSH crypto GO/CUT | `w14-factory-ssh-gate` | decided mechanically by pre-written criteria; no human call unless a licence is `depends_on_use` |
| Fleet report endpoint | `w16-hardware-fleet-reporting` | where reports go, if anywhere |
| Proxmox access + a named machine | `w15-portability-proxmox` | an API token (env only) and physical hardware |
| A Windows 11 machine | `w15-portability-wsl2` | for A3's real run |
| Physical access + serial | `w16-portability-metal` | B4/B5 |

**What "planned" does not mean.** Several plans are experiments whose outcome is unknown: F6,
V8, H7, every `generate-*`. Each states its fallback (human-written, labelled as such in the
authorship harness) so a negative result does not stall the PRD. It is published and the ladder
continues.

### Status — waves 0 through 4

22 phases implemented, each with a plan in `plans/completed/` and a report in `reports/`.

| Wave | Phases | State |
|---|---|---|
| 0 | scheduler dispatch, H0 shell hardening | done |
| 1 | intent-D corpus, intent-A index, F2 service format, F3 PMM spec, H1 inventory, H5 identity | done |
| 2 | F1 dependency audit, intent-B manifest, H2/H3 ingestion, portability start | done |
| 3 | F4 DHCP service, F5 pipeline, intent-C handoff, H4 errata table | done |
| 4 | intent-E leakage, intent-F packaging, H6 mitigations, H8 safety, H11 disclosure | done |

**What is blocked, and on what**

| Phase | Blocked on |
|---|---|
| F6 (agent-authored service), V8 (agent-authored driver), H7 (generated mitigations) | **w11 ran F6 and V8 once each: 0 lines.** The loop cannot finish a task chain: an empty diff is sent to review, the local model invents code to reject, and rejection is terminal (`engine.py:343,446`, `base_agent.py:133`). H7 is not runnable because `vmm` is phantom. See [ELIGIBILITY.md](ELIGIBILITY.md) |
| intent-G (Doom) | Spec written and input accepted in w11. Now blocked on a generated tree and a doomgeneric GPL-2.0 licence decision |
| intent-H (host this repo) | The HTTP path is unproven; F4's client exchange never worked under QEMU user networking |
| F7–F11 (storage, service ladder) | No block driver |
| H10, H12, H13, intent-I/J | Real hardware on multiple steppings. Partly unobtainable — see `agent/hardware/CONFORMANCE-HARDWARE.md` |

**Three findings that changed the plan**

1. **Corpus scoping does not improve answer quality.** Measured: in-scope garbage 20% unscoped
   vs 22% scoped. The hypothesis is refuted; scoping controls image content, not quality
   (`reports/e2e-intent-scoped-corpus.md`).
2. **The eval harness was measuring itself.** It sent prompts open-loop and scored undelivered
   ones as garbage, so a slower model looked like a worse one — which makes the recorded 22%
   rung-3b baseline suspect.
3. **`excludes` did not reach the kernel.** Found three independent ways: the reference graph,
   a scoped image still answering `what is my ip`, and a reduced slice failing to link with 10
   undefined references.

### Plans that exist

Waves 0 and 1 are planned — eight files in `.claude/PRPs/plans/`, each anchored to real
`file:line` references:

```
w0-orchestrator-scheduler-dispatch    the blocker; one diagnostic, unknown root cause
w0-agent-shell-hardening              H0; argv for internal callers, a decision for the shell tool
w1-slm-scoped-corpus                  intent-D; the cheapest hypothesis test in the set
w1-spec-capability-index              intent-A; provides/depends_on, closed slices
w1-factory-service-spec-format        F2; the format intent-C must emit into
w1-kernel-pmm-spec                    F3; the first phase written to be generated, not written
w1-hardware-vendor-inventory          H1; the landscape as data, with licensing enforced
w1-hardware-silicon-identity          H5; the join key every errata phase depends on
```

Waves 2–6 are **not** planned, and `.claude/PRPs/plans/DEFERRED.md` records why per phase:
each depends on a format wave 1 has yet to define, and inventing those formats inside a plan
file would put design in the wrong place and get it wrong twice.

### If you only plan one thing

`/prp-plan` the **scheduler fix**. It is one diagnostic log line inside `get_assignments()`
printing the ready tasks, their roles, and the agent-pool keys at the moment of the call —
enough to separate "role string does not match a pool key" from "every slot is considered
busy". Every other item in this document is cheaper on the other side of it.

### If you only plan two

Add **intent-D, the scoped corpus**. It is the cheapest falsification of the most
consequential hypothesis in the set — that the model is bad because it is general — and the
answer either removes a lot of future work or redirects it.

### w6 and w7 — hardware definition, then drivers

**The hardware-definition PRD is complete** and moved to `completed/`. All eight phases, each
with a plan in `plans/completed/` and a report in `reports/`.

Its central hypothesis was *"most hardware definitions can be derived rather than elicited"*, and
D5 measured it:

| Path | Questions asked |
|---|---|
| microVM, derived from `hypervisors.yaml` | **0** |
| AUTON-hosted, derived from `PROVENANCE.json` | **0** |
| VM, probed with `lspci`/`cpuinfo`/`dmidecode` | **0** |
| anything elicited | 4–5 |

The PRD's stated risk was "a 40-question form nobody finishes". The worst path is five, and a
test holds a ceiling of eight.

**Three things it found that were not hypotheses.**

1. **`e1000` was hardcoded into three intent rules.** Every network image AUTON could build was
   built for an Intel 82540EM whatever the machine. `[gate: capabilities]` does not catch it —
   `e1000` is mapped, so the slice resolves and the image builds with a driver bound to nothing.
   Fixed in D7; the driver now comes from the target's own devices.
2. **`drivers.md` `provides` lists exactly one network driver.** So the only machines AUTON can
   build a network image for are machines with an e1000, and a Firecracker target is refused
   outright. That is V5's justification, stated as a measurement.
3. **`firecracker.md` shipped with PCI device ids on a machine with no PCI bus.** The format
   admitted only `vvvv:dddd`, so the wrong id was the only writable one. A format that admits one
   id shape makes the wrong answer the only expressible one.

**The driver PRD is next**, and V1–V3 landed alongside w6. Three of the remaining seven are
planned:

| Plan | Phase | Why in this order |
|---|---|---|
| `w7-driver-strategy-selection` | V4 | `strategy` is a field in every record and nothing decides it. V5 should be a decision's output, not a hand-wave a record then documents |
| `w7-driver-verification-gate` | V9 | V2 made `verification` mandatory and nothing runs it. A mandatory unchecked field reads as a guarantee |
| `w7-driver-virtio-net` | V5 | The first driver chosen by V4 and checked by V9. Scoped to spec + host reference, because `kernels/` is deleted and this project does not write the kernel |

V6, V7, V8 and V10 are deferred with reasons in `plans/DEFERRED.md`. V10's is the interesting
one: it is a **data gap, not a dependency**. H4 and H6 landed and D8 built the join, but nothing
in any ingested document links a device or a driver to an erratum.

## Security work has one home

[`auton-hardware-truth.prd.md`](./auton-hardware-truth.prd.md) is the security PRD. Anything
deferred to "the security PRD" belongs there — currently the shell-injection path in
`base_agent.py`, which interpolates tool arguments into `create_subprocess_shell`. Its phase
H0 fixes that before any vendor-document ingestion, because pointing an agent loop that holds
a shell at untrusted external documents is the worst available sequencing.
