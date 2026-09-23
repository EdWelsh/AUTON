# AUTON Hardware Truth: Vendor Specifications, Silicon Errata, and Fault Discovery

> **Closed 2026-09-23. Superseded for everything still open by**
> [`auton-completion.prd.md`](../auton-completion.prd.md).
>
> Phases H7, H9, H10c, H10d, H10e are carried to **R10, R11, X2, D2**, each with the gate that decides it. The phases below record what was built and what it was measured against; nothing open is tracked here any more, so there is one place to look rather than five.

**Status**: draft
**Created**: 2026-09-12
**Depends on**: [`auton-service-kernel-factory.prd.md`](./auton-service-kernel-factory.prd.md)
(generation) and [`auton-intent-to-os-compiler.prd.md`](./auton-intent-to-os-compiler.prd.md)
(the device table this extends)
**Absorbs**: the security work deferred by `e2e-orchestrator-lane.md` (shell injection in
`base_agent.py`)

## Problem Statement

AUTON generates operating systems for silicon it knows almost nothing about. Its entire
hardware knowledge is **four PCI entries**, and it has no concept of a silicon *defect* at
all — no errata, no stepping awareness, no microcode state, no mitigation.

Silicon has bugs, and the operating system is usually the only practical place to fix them.
Intel's Pentium **F00F** bug (1997) let any unprivileged instruction sequence lock the CPU
dead; the fix was not a recall but an OS workaround — Linux remapped the IDT so the faulting
descriptor page was never touched. The Pentium **FDIV** bug (1994) returned wrong
floating-point division results and cost Intel a $475M recall. Every modern equivalent —
Spectre, Meltdown, MDS, Rowhammer, Downfall, Zenbleed, Retbleed — is mitigated in the kernel,
per silicon family, per stepping.

An OS that does not know which errata apply to the chip it is running on cannot be secure on
that chip, and cannot honestly claim to be. AUTON currently cannot name a single one.

And the detection side is more tractable than it sounds. **Both canonical Pentium defects were
found by comparing silicon against its own specification** — FDIV because prime reciprocals
came out wrong, F00F because an invalid operand wedged the core where the architecture
requires an exception. Neither needed a laboratory. Both needed a spec, a trusted reference
answer, and the discipline to compare — which an OS generated from that same spec is unusually
well placed to do, on every machine it is installed on.

Separately: every vendor specification AUTON would need is **already public**. The gap is not
access. It is that nothing ingests them, nothing keys them to silicon identity, and nothing
turns them into generated mitigations or into tests that check whether a chip actually behaves
as its own datasheet claims.

## Evidence

- **Hardware knowledge is four entries.** `slm.c` in the reference tree (tag
  `kernel-reference-v1`): `8086:100E`, `8086:10D3`, `1AF4:1000`, `1AF4:1001`.
- **No errata concept exists.** `grep -ri "errata\|microcode\|stepping"` across
  `agent/kernel_spec/` returns only incidental CPUID field documentation. There is no errata
  table, no mitigation registry, and no place to put one.
- **But the identity key is already specified.** `agent/kernel_spec/arch/x86_64.md:1624`
  documents CPUID leaf `0x1` returning family/model/stepping — exactly the key every vendor
  errata document is indexed by. The hook exists; nothing hangs off it.
- **The existing art is machine-readable and we ignore it.** Linux encodes this problem
  directly: `arch/x86/kernel/cpu/bugs.c` plus the `X86_BUG_*` flags in
  `asm/cpufeatures.h` and the family tables in `asm/intel-family.h` are, in effect, a
  curated hardware-errata database with mitigations attached. It is the same relationship
  `MODULE_DEVICE_TABLE` has to drivers — and the intent PRD already chose to mirror that
  pattern for device identification.
- **The model invents hardware facts.** 5 phantom PCI citations per 50 novel turns from the
  generated path, **0** from the deterministic path on identical input. An errata table is
  strictly more dangerous than a device table: a hallucinated erratum causes the OS to apply
  a wrong mitigation, or — worse — to report a machine as safe when it is not.
- **A known injection flaw is already deferred here.** `base_agent.py` builds shell commands
  by interpolating tool arguments into `create_subprocess_shell`. Recorded in
  `e2e-orchestrator-lane.md` as out of scope and belonging to "the security PRD". This is it.

## Vendor Landscape

The research the problem statement claims is unnecessary to *obtain* — this is what is
publicly available today, and what shape it is in. "Machine-readable" means something better
than prose PDF.

### CPU and ISA

| Vendor | Published | Errata channel | Machine-readable |
|---|---|---|---|
| **Intel** | Software Developer Manuals (4 vols), Optimization Manual, datasheets per family | **Specification Updates** per family (the canonical errata docs), `INTEL-SA-*` advisories, microcode revision guidance | Partly — advisories are structured; errata are PDF tables |
| **AMD** | AMD64 Architecture Programmer's Manual, Processor Programming Reference (PPR) per family | **Revision Guides** per family, `AMD-SB-*` bulletins | Partly |
| **Arm** | Architecture Reference Manual (ARM ARM), Technical Reference Manual per core | Errata notices per core/revision, security advisories | Partly; ARM publishes machine-readable system-register XML |
| **RISC-V International** | Unprivileged + Privileged ISA specs, extensions — fully open (CC-BY) | Per-implementation, not per-ISA | Specs available in source form |
| **IBM / OpenPOWER** | POWER ISA specification, open | Per-implementation | — |
| **SiFive** | Core complex manuals | Errata in manuals | — |
| **Loongson** | LoongArch reference manual | — | — |

### GPU and accelerators

| Vendor | Published |
|---|---|
| **Intel** | GPU Programmer's Reference Manuals per generation — unusually complete |
| **AMD** | GPU ISA documents, register headers shipped in the open driver |
| **NVIDIA** | Open GPU kernel modules and headers; full register specs not published (Nouveau documents by reverse engineering) |

### SoC and embedded

| Vendor | Published |
|---|---|
| **Texas Instruments** | Extensive public Technical Reference Manuals |
| **NXP** | Reference manuals (registration) |
| **STMicroelectronics**, **Microchip/Atmel** | Datasheets and reference manuals public |
| **Broadcom / Raspberry Pi** | BCM2835/2711/2712 peripheral documents — partial but real |
| **Rockchip**, **Allwinner** | Partial TRMs, community-maintained |
| **Qualcomm** | Largely closed |
| **Apple** | No public silicon specs; the Asahi Linux project's reverse-engineering notes are the de-facto reference |

### Buses and standards

| Body | Access |
|---|---|
| **UEFI Forum** (UEFI, ACPI) | Fully public |
| **USB-IF** | Specs public; `usb.ids` public |
| **PCI-SIG** | Base spec requires membership; `pci.ids` device registry public |
| **NVM Express** | Specs public |
| **Bluetooth SIG** | Core spec public |
| **JEDEC** (DDR/LPDDR) | Membership/registration |
| **MIPI** | Membership |
| **SD Association** | Simplified specs public |
| **IEEE 802** | Some free after an embargo period |

### Errata and vulnerability aggregation

- **NVD / CVE**, and MITRE's **CWE hardware-design view** (`CWE-1194`) — structured, queryable.
- **Linux kernel**: `cpu/bugs.c`, `X86_BUG_*`, `intel-family.h` — curated, versioned, and the
  closest thing to a machine-readable errata-to-mitigation mapping that exists.
- **Xen Security Advisories** (`XSA-*`) — frequently hardware-rooted, well written.
- **Microcode distributions**: `intel-microcode`, `amd-ucode` in `linux-firmware` — the
  revision numbers alone are a fingerprint of which errata are fixed in silicon versus patched.
- **Academic**: USENIX Security, IEEE S&P, CCS; the transient-execution attack catalogues.

**Licensing reality**: most of this is freely *downloadable* and not freely
*redistributable*. AUTON must therefore ingest and **derive** — a normalised errata table
with citations — and must not vendor the source documents into the repo. This is a hard
constraint, not a preference.

## Proposed Solution

Five parts, in dependency order.

**1. Vendor corpus ingestion.** A fetch-and-normalise pipeline per vendor: specs, errata
documents, advisories, microcode revision tables. Output is a normalised, cited, versioned
record set — never the source PDFs.

**2. The errata table.** Compiled, keyed on silicon identity
`(vendor, family, model, stepping, microcode_rev)`, shipped as a section **inside the model
file** alongside the device table — one artifact, one version contract. Each entry carries:
the defect, its observable symptom, the mitigation, the cost of that mitigation, and the
citation.

**3. Errata lineage.** The insight worth building around: **errata are not independent
events. They cluster by silicon lineage.** A defect in one stepping predicts related
behaviour in its successors and in siblings sharing a microarchitecture. FDIV and F00F are not
merely history — they are the archetypes for "arithmetic unit returns wrong results" and
"malformed instruction wedges the core", and those classes recur. Modelling families as
lineages makes the historical corpus *predictive* rather than archival, and tells the
conformance harness where to look first in silicon that has no errata published yet.

**4. Generated mitigations.** An erratum that applies to the target silicon becomes a
generated kernel mitigation, gated by a runtime identity check. This is the factory's job —
the mitigation is spec, and agents write the code. F00F is the model case: the erratum text
says "this instruction sequence on this stepping wedges the core"; the spec says "remap the
IDT so the descriptor page is never touched"; the agent generates the remap for the arches
that need it.

**5. Conformance and divergence testing.** Does the silicon do what its own specification
says? A harness that reads the normalised spec and tests the chip against it — instruction
semantics, MSR and CPUID surfaces, PCI config space, documented reset values. Divergence is
either an undocumented erratum, an undocumented feature, or a spec error. All three are worth
knowing, and this is the part that could find something before it is public.

## Key Hypothesis

**Hardware faults are a retrieval problem at runtime, a lineage problem at research time, and
a differential-testing problem at deployment.**

At runtime the OS must never reason about errata — it must look them up by exact silicon
identity, because a wrong mitigation is worse than none and a hallucinated "you are safe" is
worse still. This is the same architectural rule the intent PRD applied to device
identification, and the stakes are higher.

At research time, lineage is what makes the corpus useful. Ingesting every public errata
document from 1994 onward is only archival unless the families are modelled as lineages —
with lineage, an erratum class observed in one generation becomes a hypothesis to test in the
next.

At deployment, the chip is judged against a trusted reference rather than against the model.
FDIV was found by comparing division results to what division should produce; F00F by
comparing a fault to the fault the architecture requires. Every generated image can carry that
comparison for the silicon features it uses, which turns detection from something one
researcher does on one machine into something every deployment does on its own chip. That is
the only mechanism here with a plausible path to finding a defect before it is public, and it
has industrial precedent: mercurial cores were found this way, at fleet scale, by Google and
Meta.

## What We're NOT Building

- **Not a microarchitectural attack lab.** AUTON will not attempt to discover
  Spectre-class transient-execution side channels. That is a specialist discipline requiring
  expertise and equipment this project does not have, and claiming otherwise would be
  dishonest. See the capability boundary below.
- **Not offensive tooling.** The conformance harness tests whether silicon matches its spec.
  It is not an exploit framework, and nothing in this PRD produces one.
- **Not redistributing vendor documents.** Ingest and derive, with citations. Never vendor
  the PDFs.
- **Not hand-written mitigations.** An erratum becomes spec; agents generate the code.
  `README.md:11`.
- **Not a CVE feed reader.** Consuming NVD is table stakes; the value is keying errata to
  silicon identity and generating the mitigation.
- **Not trusting the model with a hardware fact.** Ever.

## Honest Capability Boundary

"Find the issues before the public if possible" deserves a precise answer rather than an
optimistic one.

**Plausibly findable by this project:**

| Class | Method |
|---|---|
| **Semantic conformance — does the instruction compute what the spec says** | Differential execution against a trusted software reference. **This is the FDIV class**, and it is the single most important row in this table — see below |
| **Fault conformance — does an invalid encoding raise the specified exception** | Feed the spec's illegal operand forms and assert the architected fault. **This is the F00F class** |
| Spec-versus-silicon divergence, configuration surfaces | Documented reset values, reserved-bit behaviour, MSR and CPUID surfaces |
| Undocumented register and instruction surface | Enumerate the MSR and CPUID space; compare against what the spec admits exists |
| Cross-stepping behavioural divergence | Same ISA, different stepping, different answer — this is genuinely how some errata are found |
| Config-space and descriptor-parsing robustness | Malformed PCI capability chains, USB descriptors, ACPI tables. LogoFAIL-class defects live here |
| Firmware and option-ROM trust boundaries | What the OS accepts from firmware without validation |
| Documented-but-unmitigated errata | The most valuable and least glamorous: errata already published that no OS on this silicon mitigates |

### Why the first two rows are the point

**Both canonical Pentium defects were semantic conformance failures, and both were found by
comparing silicon against specified behaviour.**

*FDIV* (1994): Thomas Nicely was computing reciprocals of primes and the answers were wrong.
The defect was five missing entries in a 1066-entry SRT division lookup table, so certain
divisor bit patterns produced incorrect quotients. Roughly one in nine billion *random*
divisions hit it — but it was perfectly reproducible for the affected operands.

*F00F* (1997): the spec says `cmpxchg8b` takes a memory operand. Given a register operand
with a `lock` prefix, the architecture requires an exception; the silicon instead issued a
locked bus cycle and wedged the core until reset.

Neither needed a lab. Both needed **a specification, a reference answer, and the discipline to
compare.** That is automatable, and it is what this PRD should be built around.

The technique is not brute force — the operand space of double-precision division is 2^128
and exhaustive testing is not a plan. What works:

- **Differential execution against a trusted software reference** — Berkeley SoftFloat for
  IEEE-754, MPFR/GMP for arbitrary precision, a second implementation for integer and SIMD
  paths. The reference is the oracle the chip is judged against.
- **Structural corner cases from the spec**, not random inputs: denormals, infinities, NaN
  payloads, powers of two, rounding-mode boundaries, and — the FDIV lesson — the boundary
  values of the *algorithm* the spec implies. A radix-4 SRT divider has a table; its
  boundaries are where to look.
- **Invalid and reserved encodings**, asserting the architected fault rather than any
  particular behaviour. F00F lives here, as does most undocumented-opcode surface.
- **Scale across a fleet** rather than depth on one machine.

**There is published precedent that this finds real defects in modern silicon.** Google's
*"Cores that don't count"* (HotOS 2021) and Meta's *"Silent Data Corruptions at Scale"* (2021)
both document **mercurial cores** — CPUs in production fleets that compute wrong answers
intermittently, found by differential testing at scale rather than in a lab. Google's
**SiliFuzz** generates fuzzing inputs and compares core behaviour to detect defects. These are
FDIV's descendants, they were found by exactly the method above, and the papers are the reason
the first two rows of that table belong in the "findable" column.

**Not findable without specialist capability, and not attempted:**

transient-execution side channels; power, EM and acoustic side channels; fault injection
requiring voltage or clock manipulation; decapsulation or physical analysis; anything needing
a lab.

The realistic claim, revised upward: **AUTON can know every published erratum for the silicon
it targets, mitigate them automatically, and — because every generated OS can carry a
conformance harness for its own chip — test whether that chip honours its own datasheet at
install time, across every deployment.**

That last part is what makes "before the public" plausible rather than aspirational. A single
researcher with one laptop finds almost nothing. A fleet of deployments each differentially
testing its own silicon against a trusted reference is how mercurial cores were found, and it
is a capability an intent-compiled OS can have by construction. It will still not find the
next Meltdown — transient-execution side channels need a different discipline — but FDIV's
descendants are exactly in range.

## Responsible Disclosure

First-class, because the conformance harness can find real defects.

1. **Nothing is published on discovery.** A divergence goes to a private record with the
   reproducer, the silicon identity, and the spec citation.
2. **Vendor first.** Report through the vendor's published security contact — Intel, AMD and
   Arm all have one — with a 90-day default embargo, negotiable on the vendor's request.
3. **Mitigate quietly.** An AUTON mitigation may ship during embargo if it does not disclose
   the defect. This is the norm and it is how Linux handled several transient-execution
   mitigations pre-announcement.
4. **Reproducers are not weapons.** A reproducer demonstrates divergence from spec. It does
   not get built into an exploit, and it is not distributed during embargo.
5. **Credit the vendor's timeline.** If a vendor disputes a finding, record the dispute
   alongside it rather than escalating.

A finding with no disclosure path is not a deliverable.

## Success Metrics

| Metric | Today | Target |
|---|---|---|
| Vendors with an ingestion pipeline | 0 | **≥6** (Intel, AMD, Arm, RISC-V, UEFI/ACPI, PCI/USB registries) |
| Errata records, normalised and cited | 0 | **≥2,000** |
| Silicon families with lineage modelled | 0 | **≥20** |
| Errata correctly applied to target silicon | n/a | **100% of records matching identity** |
| Errata facts sourced from a table, not the model | 0% | **100%** |
| Documented-but-unmitigated errata found on test hardware | unknown | **reported with a count** |
| Spec-conformance tests executed per target | 0 | **≥500** |
| Semantic (FDIV-class) tests with a trusted reference oracle | 0 | **≥200 per arithmetic unit used** |
| Fault-conformance (F00F-class) invalid encodings tested | 0 | **≥100** |
| Generated images carrying a scoped self-test suite | 0 | **100%** |
| Conformance verified at install, not just in a lab | never | **every deployment** |
| Novel divergences found | 0 | **reported honestly, including zero** |
| Shell-injection paths in the agent loop | ≥1 | **0** |

The "including zero" matters. A security PRD that can only report success will report success.

## Users & Context

Three.

**The generated OS**, at boot: it must identify its silicon exactly and apply every mitigation
that applies — with no network, no package manager, and no human.

**The operator**, in chat: *"is this machine safe?"* deserves a real answer — which errata
apply, which are mitigated, which are not, and which cannot be. The honest answer is often
uncomfortable, and the rubric already rewards honest over confident.

**The researcher**, running the conformance harness against new silicon and needing a
disclosure path for what it finds.

## Solution Detail

### Ingestion (MUST)

Per vendor: fetch, parse, normalise, cite, version. Errata documents are PDF tables; parsing
them is unglamorous and unavoidable. Two rules:

- **Every record carries its citation** — document, revision, date, page. An erratum without
  provenance is a rumour, and rumours must not reach a kernel.
- **Ingestion is re-runnable and diffable.** Vendors revise errata documents; a new revision
  adding an erratum must show up as a diff, not a silent change.

### The errata table (MUST)

```
key:        vendor, family, model, stepping, microcode_rev_min, microcode_rev_fixed
defect:     what is wrong
symptom:    what an OS or program observes
mitigation: identifier into the mitigation registry, or "none known"
cost:       performance or capability price of mitigating
severity:   vendor's, and ours if they differ
citation:   document, revision, date, page
```

`mitigation: "none known"` is a legitimate and important value. So is a record whose
mitigation costs more than the defect — the OS should say so and let the operator choose.

### Mitigation registry and generation (MUST)

Each mitigation is spec: what it does, what it costs, which arches need it, how to verify it
took effect. Agents generate the implementation; the factory's validators gate it. Runtime
application is gated on exact identity — never applied speculatively, never skipped silently.

The OS must be able to report, for the machine it is on: errata that apply, mitigations
active, mitigations declined and why, and errata with no mitigation available.

### Conformance at three stages (MUST)

Conformance is not one harness run by one researcher. It is a property carried through
fine-tuning, generation, and deployment — which is what makes fleet-scale detection possible
at all.

**1. Fine-tuning — the model learns what correct behaviour *is*.**

The corpus gains spec-derived semantics: for a given instruction and operands, what the
architecture requires. This is not so the model can compute answers — it must never be the
oracle, per this PRD's central rule — but so it can *reason about divergence*: explain what a
failing test means, which erratum class it resembles, and what a plausible mitigation is.

The training pairs are `(spec clause → architected behaviour → observed behaviour →
classification)`. Historical errata supply the labelled examples: FDIV is a labelled instance
of "arithmetic unit returns wrong result for a subset of operands", F00F of "invalid encoding
fails to fault". That is the errata-lineage corpus doing double duty.

**2. Creation — the generated kernel embeds its own conformance suite.**

The factory already generates per-image marker sets. It also generates, from the spec subset
the manifest selected, a **self-test suite for exactly the silicon features that image uses**.
An image that does floating-point arithmetic carries FDIV-class tests. An image that does not
touch the FPU carries none — the suite is intent-scoped like everything else.

This is the same discipline as the rest of AUTON: the tests are spec, agents generate them,
and the validators gate them. A generated kernel that cannot self-test the silicon features
it depends on is incomplete.

**3. Deployment — the OS verifies the chip it actually landed on.**

At install time, and on demand from chat:

```
auton> is this machine safe?
  silicon:     GenuineIntel family 6 model 151 stepping 2, microcode 0x429
  errata:      14 apply, 12 mitigated, 1 declined (cost), 1 no mitigation known
  conformance: 487 of 487 spec clauses honoured
```

A conformance failure at install is the interesting case. It means one of three things, and
the OS must not guess which: an undocumented erratum, a defective individual part, or a bug
in the test. All three are worth reporting, and the third is why every assertion cites the
spec clause it tests.

**Why this ordering matters.** A conformance suite that only exists in a researcher's
repository tests the machines a researcher owns. One generated into every image tests every
machine AUTON is ever installed on — which is the only mechanism in this document that could
plausibly beat the public to a defect, and the same mechanism by which mercurial cores were
found in Google's and Meta's fleets.

### Conformance harness (SHOULD)

Reads normalised spec records and tests the silicon. Structured so a divergence is
*mechanically* distinguishable from a test bug: every assertion cites the spec clause it
tests, and a failure reports both the expectation and its source.

Runs on real hardware, which makes this the first part of AUTON that genuinely needs the
portability work in [`auton-windows-linux.prd.md`](./auton-windows-linux.prd.md) — QEMU
implements an idealised CPU and will not reproduce silicon divergence.

### Agent-loop hardening (MUST, absorbed)

`base_agent.py` interpolates tool arguments into `create_subprocess_shell`. Agents are about
to be pointed at vendor documents — untrusted external input — while holding a shell. Fixed
with argument-vector execution and no shell, before any ingestion runs.

## Implementation Phases

Prefixed `H` to avoid collision with the factory (`F`) and intent (`A`–`J`) phases.

| # | Phase | Deliverable | Depends on |
|---|---|---|---|
| H0 | **Shell hardening** | `_run_shell` takes an argv, never a shell string. Absorbed from the orchestrator lane | — |
| H1 | Vendor inventory | The landscape table above, machine-readable: vendor, documents, URLs, licence, update cadence | — |
| H2 | Ingestion — Intel + AMD | Specification Updates and Revision Guides normalised with citations | H0, H1 |
| H3 | Ingestion — Arm + RISC-V | Errata notices; RISC-V specs from source | H0, H1 |
| H4 | Errata table format | Schema, compiled layout, model-file section, `VERSION` bump | H2 |
| H5 | Identity at boot | Exact silicon identity: CPUID family/model/stepping, microcode revision, board/vendor via SMBIOS/DT | — |
| H6 | Mitigation registry | Mitigations as spec, with cost and a verification method | H4 |
| H7 | Generated mitigations — **blocked on a VMM**; the memory-manager generation run is what unblocks it. Registry, gates and scoring rule all exist | Agents implement from spec; validators gate; F00F-class IDT remap as the worked example | H6, **F5** |
| H8 | "Is this machine safe?" | The OS reports applicable, mitigated, declined, and unmitigatable errata | H5, H7 |
| H9 | Errata lineage — **tooling complete** (`lineage.py`, `retrodict.py`, `erratum-classes.yaml`, tests; both refuse below two documents). **Blocked on six Intel spec-update PDFs** a person must download: Intel's CDN refuses scripted fetches | Families as lineages; erratum classes; historical corpus made predictive | H2, H3 |
| H10 | Conformance harness — **complete host-side**: SoftFloat oracle pinned by commit and self-tested against the FDIV quotient, 28 clause-cited entries, verdicts carrying their clause into disclosure | Spec-clause-cited tests; runs on real hardware | H1, H5 |
| H10a | **Semantic conformance** — **built; 23/23 match the oracle bit-for-bit**, measured under Rosetta (a translator, not silicon, and labelled so). The x86 CI job that asserts it did not SKIP is unrun: the branch is unpushed | Differential execution against SoftFloat/MPFR; spec-derived corner cases; the FDIV class | H10 |
| H10b | **Fault conformance** — **built, Linux-only**. On macOS the control (a plain NOP) faulted, so the venue refuses to report at all rather than pass every #UD for the wrong reason | Invalid and reserved encodings assert the architected exception; the F00F class | H10 |
| H10c | **Generated self-tests** — **selection complete** (`conformance_select.py`, by disassembly, explicit mnemonic table); it found and closed a real gap (the kernel executes DIVSS/SQRTSS, uncovered). The in-kernel runner needs a generated tree | The factory emits an intent-scoped conformance suite per image | H10a, H10b, **F5** |
| H10d | **Install-time verification** — **not built**: it needs H10c's in-kernel runner inside a generated image | Every deployment tests its own silicon and can report it in chat | H10c, H8 |
| H10e | **Fleet reporting** — **complete except the endpoint**: allowlist schema, local aggregator, consent dialogue specified (default no). Where a report goes is an owner decision, written up in `decisions/fleet-endpoint.md` | Divergences aggregate across deployments, with consent. Scale is the mechanism | H10d, H11 |
| H11 | Disclosure pipeline | Private records, vendor contacts, embargo tracking | H10 |
| H12 | Unmitigated sweep — *complete: 51 of 94 ADL errata documented-unmitigated (Linux+FreeBSD, exact id/title, 2026-09-22); [report](../../reports/w13-hardware-unmitigated-sweep-report.md)* | Published errata that no OS mitigates on the test fleet. Report with a count |
| H13 | Device table merge — **complete**, [report](../../reports/w13-hardware-table-merge-report.md) | Fold the intent PRD's device table and this errata table into one shipped section | **I** (intent PRD) |

**H0 first, without exception.** Pointing an agent loop that interpolates into a shell at
externally fetched vendor documents is the worst sequencing available in this document.

## Open Questions

1. **Is PDF errata parsing tractable at quality?** Intel's Specification Updates are tables
   in PDFs with inconsistent layout across a decade. If parsing is unreliable, the fallback is
   human-curated extraction for the top families and honest coverage numbers — which is still
   far better than four device entries.
2. **How much of Linux's `cpu/bugs.c` should be mirrored versus derived?** It is GPL-2.0;
   reading it as a *reference for which errata matter* is ordinary engineering, copying its
   code is a licensing decision AUTON should make deliberately rather than accidentally.
3. **Does the errata table belong in the model file?** It is consistent with the device table,
   but errata change on a vendor's schedule rather than a training schedule. An updatable
   section, or a second module, may be more honest.
4. **What is the minimum fleet for conformance testing?** Divergence needs multiple steppings
   of the same family to be interesting. One laptop finds almost nothing.
5. **Can lineage prediction be evaluated?** The honest test is retrodiction: hide errata after
   a date, ask whether lineage would have pointed at them. If it cannot retrodict, it cannot
   predict.
6. **What does AUTON do with an erratum whose only mitigation is "do not use this silicon"?**
   Some are. The OS should probably say exactly that.

## Decisions Log

| Decision | Rationale |
|---|---|
| Errata facts by table lookup only | Measured: 5 phantom hardware citations per 50 turns from generation. A hallucinated erratum applies a wrong mitigation or falsely reports safety |
| Ingest and derive; never redistribute vendor documents | Most specs are freely downloadable and not freely redistributable |
| Every errata record carries a citation | An erratum without provenance is a rumour, and rumours must not reach a kernel |
| Transient-execution research explicitly out of scope | It needs specialist expertise and equipment. Claiming it would be dishonest, and the honest scope is still substantial |
| Responsible disclosure is a deliverable, not a policy note | The conformance harness can find real defects; a finding with no disclosure path is not a deliverable |
| Report zero findings as a finding | A security effort that can only report success will report success |
| H0 (shell hardening) precedes all ingestion | Agents are about to hold a shell while reading untrusted external documents |
| `mitigation: "none known"` is a first-class value | Honest degradation is the project convention, and it applies to silicon too |
| Semantic and fault conformance are the priority rows, not configuration surfaces | Both canonical Pentium defects were semantic failures found by comparing silicon to spec. An earlier draft scoped conformance to reset values and reserved bits and missed the FDIV class entirely |
| Conformance is generated into every image, not kept in a lab | A suite in one repository tests one researcher's machines. A suite in every deployment tests every machine — the mechanism by which mercurial cores were actually found |
| The model learns spec semantics but is never the oracle | It must be able to classify a divergence and propose a mitigation. It must never be what a chip is judged against; that is SoftFloat, MPFR, or a second implementation |

## Research Summary

- **The archetypes are old and still instructive.** FDIV (1994) — wrong arithmetic results,
  mitigated in software by avoiding the affected path. F00F (1997) — a malformed instruction
  sequence wedging the core, mitigated by Linux remapping the IDT so the descriptor page was
  never touched. Both are OS-layer fixes for silicon defects, which is precisely the capability
  this PRD adds. The modern catalogue — Spectre, Meltdown, MDS, Rowhammer, Plundervolt,
  Downfall, Zenbleed, Retbleed, LogoFAIL, PACMAN — differs in mechanism, not in who has to fix
  it.
- **The existing machine-readable art is Linux's**, in `arch/x86/kernel/cpu/bugs.c`,
  `asm/cpufeatures.h` (`X86_BUG_*`) and `asm/intel-family.h`. It is curated, versioned, and
  tied to exact families. Treating it as the reference for *which errata matter operationally*
  is the fastest honest start, with the licensing question recorded above.
- **Access is not the constraint.** Intel, AMD, Arm, RISC-V International, the UEFI Forum,
  USB-IF, NVM Express and the Bluetooth SIG all publish freely. PCI-SIG, JEDEC and MIPI gate
  the base specifications behind membership while the device registries stay public.
  Apple silicon is the notable hole, where the Asahi Linux project's documentation is the
  de-facto reference.
- **FDIV and F00F were both found by spec comparison, not by a lab.** FDIV: five missing
  entries in a 1066-entry SRT division table, discovered by a mathematician whose prime
  reciprocals came out wrong. F00F: `lock cmpxchg8b` with a register operand, where the
  architecture requires an exception and the silicon wedged instead. A specification, a
  reference answer, and the discipline to compare.
- **The modern continuation is documented and industrial.** Google's *"Cores that don't
  count"* (HotOS 2021) and Meta's *"Silent Data Corruptions at Scale"* (2021) describe
  **mercurial cores** — production CPUs computing wrong answers intermittently — found by
  differential testing across fleets. Google's **SiliFuzz** fuzzes and compares core
  behaviour to detect defects. These establish that the FDIV method still works on current
  silicon, and that **scale substitutes for laboratory capability** in this one class.
- **The oracle problem is the crux.** Differential testing needs something trusted to compare
  against: Berkeley SoftFloat for IEEE-754, MPFR/GMP for arbitrary precision, or a second
  independent implementation. Without an oracle a conformance suite only detects
  self-inconsistency, which is a much weaker signal.
- **Microcode revisions are an underused signal.** `intel-microcode` and `amd-ucode` revision
  numbers distinguish "fixed in silicon" from "patched at boot" from "unpatched", which is
  exactly the distinction an operator asking *"is this machine safe?"* needs and rarely gets.
