# AUTON: Intent to Operating System

**Status**: draft
**Created**: 2026-09-12
**Layer**: the user-facing intent surface. The generation engine beneath it is
[`auton-service-kernel-factory.prd.md`](./auton-service-kernel-factory.prd.md) — read that first.
**Supersedes**: `auton-real-world-deployments-and-silicon.prd.md` (removed; its grounding fix, device-table design and scenario list were carried into this document)

> **Scope boundary.** The factory PRD answers *"how does one minimal bootable image get
> generated from a spec?"* — manifest-driven builds, a `kernel_spec/services/` format, the
> agent loop, the three validators, the storage unlock, and a six-service ladder. This PRD
> does not restate any of that. It answers the layer above: *"how does a sentence a person
> typed become the spec the factory consumes, and how does the model shipped inside the image
> get scoped to it?"*
>
> An earlier draft of this PRD duplicated the factory's generation design. That has been
> removed; the factory's framing is older, sharper, and canonical.

## Problem Statement

The factory takes a service name: `auton build-service dns`. A person does not have one. They
have a sentence:

```
AUTON train "I want to play Doom" --output ./Doom
```

Nothing turns that sentence into a service spec, and nothing scopes the SLM shipped inside
the image to it. Today every build trains the model on the same 555-record general corpus
covering all six intent classes, so a Doom image would carry a model that answers questions
about kubernetes roadmaps — and answers them badly, because generality is what makes it bad.

The cost of not solving it: AUTON can generate purpose-built kernels but only for services
someone has already named and specced, and every image ships the same oversized,
under-performing general model.

## Evidence

- **The factory's entry point takes a service name**, not an intention
  (`auton build-service <name>`, factory PRD phase 5). There is no path from
  *"I want to play Doom"* to a manifest.
- **No intent scoping exists anywhere.** `SLM/tools/build_corpus.py` generates one corpus
  covering all seven intent classes — 555 records — regardless of target. There is no
  `--intent` flag and no manifest to read one from.
- **Generality is measurably the problem.** Rung 3b scored 78% correct-or-honest / 22%
  garbage. Escalating 6M → 48M parameters gave 74%/26%: capacity is not the constraint.
  Phase 7 sessions found the neural model answering 23 of 50 novel turns against the rule
  engine's 16, with **all 9** turns where it answered and rule deflected being wrong
  (`i need gpu access` → the NIC; `can i run nginx` → the kubernetes roadmap).
- **The model invents hardware.** 5 phantom PCI citations per 50 novel turns from the
  generated path, **0** from the deterministic path on identical input. Root cause is our own
  corpus (`build_corpus.py:37` teaches ids absent from the bus) *and* the spec, which until
  this week instructed the kernel to ask the model what a device is.
- **Device knowledge is four entries** (`slm.c` in the reference tree, tag
  `kernel-reference-v1`). An image installed on real hardware needs a real table.
- **There is no tracked kernel tree.** `kernels/` is gitignored as generated output; the
  reference is tag `kernel-reference-v1`, its structure is in
  `agent/kernel_spec/reference/x86_64/`, and its contracts are in `agent/kernel_spec/`. The
  spine takes `--target <dir>` and validates whatever was produced.

## Proposed Solution

Three stages in front of the factory, one behind it.

```
  "I want to play Doom"
    │
    ├─1─ intent → capability manifest     requires: framebuffer, input, allocator,
    │                                     module asset, slm, terminal
    │                                     excludes: net, tcp, http, dns, writable-fs
    ├─2─ manifest → service spec          written into kernel_spec/services/, the
    │                                     format the FACTORY already consumes
    │        ╎
    │        ╎  ... factory generates, builds, and validates the image ...
    │        ╎
    ├─3─ manifest → scoped SLM corpus     train only the intents this image serves
    └─4─ package                          installer + ISO + model + provenance in <dir>
```

Stage 2 is a handoff, not an implementation: it emits the factory's existing spec format. The
work in this PRD is stages 1, 3 and 4, plus the device table that any installed image needs.

## Key Hypothesis

**Scoping the model to one intent fixes the quality problem that scale did not.**

Most measured garbage was cross-intent mis-routing — a driver question answered with a DHCP
lease, an nginx question answered with the kubernetes roadmap. Those intent classes cannot
collide in an image that only serves one of them. If that is right, a Doom image's model
needs perhaps twenty intents and could be excellent at them at a fraction of 6M parameters.

Cheap to falsify: build the scoped corpus (stage 3) and re-score before touching anything
else.

Corollary: **capability leakage is a build failure.** If the Doom image links a TCP stack, the
manifest's `excludes` was not enforced. That is checkable on the artifact, which makes
"minimal" falsifiable rather than aspirational.

## What We're NOT Building

- **Not the generation engine.** Manifest-driven builds, the service-spec format, the agent
  loop, validators, the storage unlock, and the service ladder are all the factory's.
- **Not hand-written kernel code.** Any capability an intent needs is expressed as spec.
  `README.md:11` — *"We don't write the kernel. The agents do."*
- **Not multi-intent images in v1.** One sentence, one output directory.
- **Not a general-purpose OS.** No POSIX, no libc, no shell. Chat plus a terminal.
- **Not shipping copyrighted assets.** A Doom image needs a WAD; the manifest names it and the
  user supplies it.

## Success Metrics

| Metric | Today | Target |
|---|---|---|
| Sentences compilable to a bootable image | 0 | **≥5** |
| Capability leakage (excluded subsystem present in the artifact) | n/a | **0** |
| Corpus records in a single-intent image | 555 (all classes) | **scoped; measurably fewer** |
| Garbage rate, scoped model | 22% | **<10%** |
| Phantom hardware citations | 5 / 50 turns | **0** |
| Device table entries | 4 | **≥30,000 PCI + ≥5,000 USB** |
| Correct driver selected, hardware absent from the corpus | untested | **≥90%** |
| Two different intents produce measurably different image sizes | identical | **yes** |

## Users & Context

One user, one sentence. They do not want an operating system; they want Doom. AUTON's job is
the smallest image that gets them there, and to say precisely which capability is missing when
it cannot.

The second user is the factory. It needs a service spec, and this PRD's job is to produce one
from a sentence.

## Solution Detail

### Stage 1 — Intent to capability manifest (MUST)

```
intent:   "I want to play Doom"
requires: boot, mm(allocator), dev(pci), drivers(framebuffer, input),
          slm(scoped), sys(terminal), pkg(module-asset)
excludes: net, ipc, fs(writable), sched(preemptive)
assets:   doom.wad          (Multiboot2 module, user-supplied)
markers:  "[FB] mode set", "[INPUT] keyboard ready", "[DOOM] frame 1"
```

`excludes` is the load-bearing field — without it "minimal" cannot be tested. `markers` feeds
the factory's per-image marker sets and the spine's assertions.

Requires a **capability index** the subsystem specs do not yet carry: each section tagged with
what it provides and what it depends on, so a slice is closed under dependency. This is the
one spec change everything else rests on.

### Stage 3 — Scoped SLM corpus (MUST)

`build_corpus.py --manifest <manifest>`: generate only the intents the image serves, and
inherit `excludes` — an image with no network ships no corpus records about DHCP leases.

Two predictions, both cheap to check:

- The corpus shrinks, so the model shrinks, so the boot module shrinks and the RAM floor drops.
- **The garbage rate falls without any modelling change**, because the intent classes that were
  mis-routing into each other no longer coexist.

Grounding is mandatory regardless: device facts come from a table, never from the model.

### Stage 4 — Packaging (MUST)

`<output>/` contains the bootable ISO, an installer, the scoped model and its manifest, the
generating spec subset, and a provenance record — which agent wrote which file, and which spec
section each implements. A human must be able to review generated kernel code without reading
it blind.

### Device knowledge (MUST)

Any image installed on real hardware must select drivers for the machine it lands on.
**Identification is retrieval, not generation** — now specified in
`agent/kernel_spec/subsystems/dev.md`:

enumerate from silicon (PCI / USB / device-tree / ACPI, already abstracted by the Device
Discovery HAL) → exact lookup in a compiled table shipped inside the model file → driver name
plus availability. On a miss, the answer echoes the id read from the bus. The SLM classifies
intent and phrases the answer; it has no mechanism to emit a device id.

Driver availability has three states, and **"known but not built" is a normal outcome** for a
scoped image rather than a failure.

The same table is extended with silicon **errata** by
[`auton-hardware-truth.prd.md`](./auton-hardware-truth.prd.md) — keyed on
`(vendor, family, model, stepping, microcode_rev)` rather than device id, and subject to the
same rule: a fault is looked up, never generated. A hallucinated erratum is worse than a
hallucinated device name, because it makes the OS apply a wrong mitigation or report a machine
as safe when it is not.

### The intent corpus

Each row is an `AUTON train` invocation and an end-to-end test, graded by an **external
probe** — not by whether the chat answer sounded right.

| # | Sentence | Distinguishing capability | Probe |
|---|---|---|---|
| I1 | *"I want to play Doom"* | framebuffer + input, **no network** | Non-blank frame; input accepted |
| I2 | *"host this repo"* | net + http, **no writable storage** | `git clone` the served URL, diff against HEAD |
| I3 | *"send an email and receive all my emails"* | smtp + imap + writable store | Message arrives in a real mailbox; inbound fetch returns it |
| I4 | *"a database for user info with RBAC and OAuth"* | tls + crypto + writable store | OAuth round-trip; low-privilege query **refused**, admin query succeeds |
| I5 | *"I want to interact with yedgi.com"* | tls + http client + framebuffer | Page title matches; a form submits; screenshot captured |
| I6 | *"my laptop won't connect to wifi, fix it"* | device table + wifi driver | Correct driver for real silicon; association succeeds |

I1 and I2 come first: I1 needs no network, I2 needs no storage, and between them they cover
both axes and prove `excludes` is enforced in both directions. I3, I4 and I6 map onto factory
services (email, database, drivers) and should follow its ladder rather than race it.

Grading uses the chat rubric lifted to deployments: **worked** (probe passes), **honestly
refused** (names the missing capability), **failed** (claimed success without the probe
passing, or errored). Claiming success while the probe fails is the deployment-level
equivalent of garbage and scores worst.

## Technical Approach

- **Capability index**: front-matter on each subsystem spec section declaring `provides` and
  `depends_on`.
- **Leakage check**: inspect the generated tree and the linked artifact for symbols belonging
  to excluded subsystems. A Doom image containing `tcp_connect` fails the build. The factory's
  composition validator is the natural home.
- **Device table**: sorted identity keys plus a string pool, binary-searchable as mapped
  bytes, shipped as a section **inside the model file** — one artifact, one version contract,
  no way for model and table to drift. Scoped by manifest: a Doom image needs input and
  display entries, not every NIC ever made.
- **Spine integration**: `scripts/e2e.sh --target <output>` already validates an arbitrary
  tree. It needs two additions: assert the intent works (a frame rendered, a repo cloned) and
  assert no excluded subsystem is present.
- **Security**: the orchestrator's `_run_shell` interpolates tool arguments into
  `create_subprocess_shell` (`base_agent.py`). Agents are about to generate far more code
  through that path; it must be fixed before generation runs on anything but hand-written
  intents. OAuth secrets for I4 come from the environment, never a corpus or a transcript.

## Implementation Phases

Numbered to avoid collision with the factory's phases, which are cited as `F<n>`.

| # | Phase | Deliverable | Depends on |
|---|---|---|---|
| A | Capability index | `provides` / `depends_on` front-matter across the subsystem specs; closed-slice computation | — |
| B | Intent to manifest | A sentence parsed to requires/excludes/assets/markers | A |
| C | Manifest to service spec | Emit the factory's `kernel_spec/services/` format | B, **F2** |
| D | Scoped corpus | `build_corpus.py --manifest`; grounding fix folded in; garbage re-measured | B |
| E | Leakage enforcement | Excluded-subsystem symbols fail the build | C, **F5** |
| F | Packaging | `--output <dir>`: ISO, installer, scoped model, spec subset, provenance | C, E |
| G | I1 Doom — **spec + input decision done, still blocked**, [report](../reports/w11-intent-doom-report.md): needs a generated tree and a doomgeneric (GPL-2.0) licence decision — *planned: [`w14-intent-doom-boots`](../plans/completed/w14-intent-doom-boots.plan.md)* | `AUTON train "I want to play Doom" --output ./Doom` boots and plays | F |
| H | I2 host-this-repo — *planned: [`w14-intent-host-repo`](../plans/completed/w14-intent-host-repo.plan.md)* | Second intent, disjoint capabilities; image sizes measurably differ | F |
| I | Device table — **complete**, [report](../reports/w10-intent-device-table-report.md) | Compiled PCI/USB table in the model file; retrieval-only device facts | D |
| J | I6 real silicon — *planned: [`w15-intent-real-silicon`](../plans/completed/w15-intent-real-silicon.plan.md)* | Driver selection on hardware absent from the corpus | I |

**Blocked on the factory**: C needs F2 (spec format), E needs F5 (validator wiring), and
everything downstream of generation needs the agent loop to dispatch at all — currently
`get_assignments()` returns empty on every iteration while a ready task and an idle developer
agent both exist. That defect gates both PRDs and is the single highest-leverage fix in the
repo.

**Not blocked**: A, B and D are spec and Python work that can proceed immediately, and D is
the cheapest test of this PRD's central hypothesis.

## Open Questions

1. **Does scoping fix the garbage rate for free?** Predicted yes; phase D answers it cheaply.
   If it does not, the SLM quality problem is deeper than generality and the 22% may be a
   6M-parameter ceiling.
2. **How small is a Doom image?** If the generated tree is the same size as the general one,
   the slice is not really slicing.
3. **Does the terminal belong in the slice?** Every intent gets "SLM + terminal", so it may be
   a common base rather than a per-manifest capability.
4. **Is a sentence enough?** *"I want to play Doom"* does not say which display resolution or
   input device. The manifest may need defaults plus a clarifying question — which the chat
   surface is well suited to ask.
5. **How much of `pci.ids` ships?** Full is ~36k devices and simple; a manifest-scoped subset
   is smaller but needs a defensible selection rule.
6. **What is the minimum viable installer?** A raw ISO is simplest. Real hardware needs disk
   partitioning, which needs writable storage — which most intents exclude.

## Decisions Log

| Decision | Rationale |
|---|---|
| This PRD is the intent layer only | The factory PRD is older, sharper, and already covers generation. An earlier draft of this document duplicated it; the duplication was removed rather than reconciled |
| The entry point takes a sentence, not a service name | A person has an intention. `build-service dns` requires someone to have already decided the answer |
| `excludes` is mandatory in every manifest | Without it "minimal" is unfalsifiable; with it, leakage is a build failure |
| Device facts by retrieval only | Measured: 5 phantom citations / 50 turns from generation, 0 from lookup. Scaling a 4-entry table to 36,000 under an active hallucination defect is the worst sequencing available |
| Scoped corpus before any modelling work | It is the cheapest test of the central hypothesis, and it may fix the garbage rate at no cost |
| Intents graded by external probe | "Did it answer well" is what we already measure, and it did not stop 9 of 9 wrong answers on novel input |

## Research Summary

- The factory PRD's key observation — **AUTON is already a unikernel** (single address space,
  identity-mapped, no process model, one purpose per image, library-OS composition, boots on a
  hypervisor) — is why scoping is cheap rather than a rewrite. It also explains why a
  kernel-native Doom needs no process model: there is nothing to isolate it from.
- Multiboot2 lets GRUB hand a kernel a linear framebuffer and arbitrary file modules, and the
  reference tree's `boot_info.c` already walks that tag list. I1 therefore needs neither a
  filesystem nor a display driver — the two capabilities it looks like it needs.
- `pci.ids` and `usb.ids` are the canonical public device-identity sources. No comparable
  single source exists for driver *mapping*; Linux encodes it per-driver in
  `MODULE_DEVICE_TABLE`, which the device table mirrors.
- `README.md` cites NVIDIA VibeTensor — ~195K lines of agent-generated system software without
  human code review — as the existence proof for generation. Consistent with what we measured:
  tool-calling 8/8, dispatch 0. The bottleneck is orchestration, not model capability.
