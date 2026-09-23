# Deferred Plans — Waves 2 through 6

Waves 0 and 1 are planned: eight files in this directory, every task anchored to a real
`file:line` that exists today. Waves 2–6 are **not** planned, deliberately.

## Why

A PRP plan is only useful if its "Patterns to Mirror" and "Files to Change" tables point at
something real. Every completed plan in `completed/` does — `cli.py:28-47`,
`brain.py:36-61`, `neural_parity.sh:18-45`. That is what makes a plan executable rather than
aspirational.

Every wave-2+ phase depends on an artifact that **does not exist yet**, and in most cases on
a *format* that wave 1 is going to define. Writing those plans now would mean inventing the
formats in a plan file, which is the wrong place to design them — and they would then be
wrong, because wave 1 will define them differently once it meets reality.

The specific missing inputs are below. Each entry says what unblocks it and what its plan will
be able to cite once it does. Nothing is lost; the reason is recorded.

## Wave 2

| Phase | Waiting on | Its plan will cite |
|---|---|---|
| **F1** dependency audit + manifest | The manifest format is F1's own output, but its input — measured coupling — already exists in `reference/x86_64/graph.json`. **This one is nearly plannable now**; it waits only on F2's spec format so the manifest and the spec agree | `graph.json` subsystem edges; F2's format |
| **intent-B** intent → manifest | **intent-A's capability vocabulary.** A manifest lists `requires`/`excludes` in terms of capability names that do not exist until A declares them | `capability_slice.py`; the front-matter schema |
| **H2/H3** vendor ingestion | **H1's `vendors.yaml`** — the document identities, forms and licences ingestion parses. Also H0, because ingestion fetches untrusted documents while agents hold a shell | `vendors.yaml` records; H0's argv interface |
| **windows-linux** start | Nothing blocks it. It is unplanned here only because it is a whole PRD, not a phase — plan it from its own document when a second host is available |

## Wave 3

| Phase | Waiting on | Its plan will cite |
|---|---|---|
| **F4** first service, human-authored | **F2's format and `dhcp.md`.** F4 implements against that spec; without it there is nothing to implement against | `services/dhcp.md`; F1's manifest; `tests/kernel/` harnesses |
| **F5** factory pipeline + gates | **F4** — the pipeline generalises what F4 did by hand. Generalising before there is one instance is how you build the wrong abstraction | F4's build path; `scripts/e2e.sh --target`; the three validators |
| **intent-C** manifest → service spec | **F2's format** (the target) and **intent-B** (the source). Pure handoff, and both ends are undefined | `service_spec.py`; intent-B's manifest schema |
| **H4** errata table format | **H2's normalised records.** A table schema designed before seeing real Intel Specification Update rows will not survive contact with them | H2's record shape; H5's identity structure |

## Wave 4

| Phase | Waiting on | Its plan will cite |
|---|---|---|
| **F6** agent-authored service | **The scheduler fix (wave 0) and F5.** This is the phase that tests `README.md:11`, and it cannot be planned in detail until we know what F5's pipeline looks like | F5's pipeline; the cost comparison against F4 |
| **intent-E** leakage enforcement | **F5's validators** — leakage is a validator, and it needs somewhere to live | The composition validator; intent-A's slice |
| **intent-F** packaging | **intent-C** — you cannot package what has not been generated | Generated tree layout; provenance format |
| **H6/H7** mitigation registry and generation | **H4's table** and **F5's gates** | Errata records; the mitigation spec format |

## Wave 5

| Phase | Waiting on |
|---|---|
| **intent-G** I1 Doom | All of intent-A→F. Its plan is mostly Multiboot2 framebuffer, PS/2 input, and doomgeneric's six functions — but as *spec*, generated. Roughly 400 lines, and the tree confirms none of storage, ring-3 or a VESA driver is needed |
| **intent-H** I2 host this repo | Same chain; disjoint capabilities, which is the point |
| **H8** "is this machine safe?" | H5 identity plus H7 mitigations |
| **F7–F11** storage and the service ladder | F3's PMM, then F5 |

## Wave 6

| Phase | Waiting on |
|---|---|
| **H10 + H10a–e** conformance | **Real hardware** (windows-linux) and H1's spec sources. The oracle choice — SoftFloat, MPFR, or a second implementation — is a design decision that belongs in that plan, not this note |
| **H11** disclosure pipeline | H10, but should be *written* before H10 runs. A harness that can find a defect with no disclosure path is not ready to run |
| **intent-I/J**, **H12/H13** | The device and errata tables, and their merge |

## w6 — hardware definition and drivers

Wave A landed (D1, D6, D3, D2, V1+V3 — plans in `completed/`). Three of the four remaining
eligible phases are now planned, because D1 gave them a real format to cite:

| Phase | Plan | Unblocked by |
|---|---|---|
| D7 capability join | `w6-target-capability-join` | D1's `Device.role` |
| D4 probe ingest | `w6-target-probe-ingest` | D1's format, V3's `device_registry.identify` |
| D8 errata join | `w6-target-errata-join` | D1's `silicon` block with a mandatory `source` |
| V2 driver decision record | `w6-driver-decision-record` | D1 — the format it mirrors |

**D5 elicitation is deliberately not planned.** It is the only remaining phase whose input does
not exist: what elicitation must ask is exactly the complement of what D4's probe can answer, and
that boundary is D4's output. Writing the plan now would mean deciding in a plan file which facts
a probe yields — the same mistake this document exists to prevent. The PRD already says D5 is
last on purpose; the metric is how rarely it is reached, and that number is not knowable until
D2, D3 and D4 are all running.

## w7 — driver development

The hardware-definition PRD is complete (`prds/completed/`), which unblocked the driver PRD
entirely. V1, V2 and V3 landed in w6. Three of the remaining seven are now planned:

| Phase | Plan | Unblocked by |
|---|---|---|
| V4 strategy selection | `w7-driver-strategy-selection` | V2's `strategy` field, V3's identification, H1's inventory |
| V9 verification harness | `w7-driver-verification-gate` | V2's mandatory `verification`, F5's gate pattern |
| V5 virtio-net | `w7-driver-virtio-net` | V2's record; scoped to spec + host reference, since `kernels/` is gone |

**Four are not planned, and the reasons differ.**

| Phase | Waiting on | What its plan will cite |
|---|---|---|
| **V6** virtio-blk | **V5.** Same transport, same ring arithmetic, same verification harness — and the whole point of V5 being the control is that V6 costs less. Planning both together would lose that measurement | V5's spec section, its host reference, and its recorded cost |
| **V7** framebuffer + input | **V5**, for the pattern, and a decision V5 will force: whether a driver with no open specification can be `synthesize` at all. VESA has one; a modern GPU does not | V4's refusal path applied to a device with no spec |
| **V8** agent-authored driver | **F6**, which is blocked. The loop can dispatch, but an architect overwrote `net.h` with a placeholder — workspace isolation and write granularity come first. Also V5, which is its control | F6's isolation fix; V5's cost figures |
| **V10** errata join | **A data gap, not a dependency.** H4 and H6 landed and D8 built the join, but *nothing links a device or a driver to an erratum.* `vendor_ingest.Record` carries `applies_to` identity keys, `status`, `workaround` and `detail` — no capability and no device. Every errata document in `vendors.yaml` is a CPU or SoC errata sheet. Closing it means a new field on driver records, and V2's format rule is that a field is added when a second record cannot be expressed without it — not in anticipation. The evidence to justify it does not exist yet | a real erratum/driver pair, once one is found |

D8 hit this same wall and is worth reading first: its plan asked for a refusal conditioned on
"the image uses the affected capability", and that condition turned out not to be computable.
The report says so rather than faking the link. V10 is the same problem one level down.

## The rule going forward

Plan a wave when the wave before it has landed, not before. If a plan cannot cite a real
`file:line` for its patterns, it is a design document wearing a plan's clothes — and the
formats it would invent belong in the spec, where they can be reviewed as contracts rather
than buried in a task list.

## w11 — all five plans closed (2026-09-21)

No plan remains open in this directory. Reports are in `../reports/w11-*`, and the pre-registration
for the authorship runs is `../reports/w11-authorship-preregistration.md`.

Nothing is deferred *from* w11 in the sense this file uses. What remains is blocked on work no
PRD yet contains: the agent loop's review path, a named kernel base, a VMM, and two decisions
only a person can take. `../prds/ELIGIBILITY.md` lists them. Write those phases into a PRD before
planning them, so the rule above holds: a plan cites a `file:line` that exists, and designs no
format of its own.

## w13–w15 — what is deferred now, and what it waits on (2026-09-22)

Everything host-side is built. Three kinds of blocker remain, and each entry says which.

| Deferred | Kind | Waiting on | What exists already |
|---|---|---|---|
| **V10** errata join | data | **One Intel NIC specification update.** `curl` gets 403 from Intel's CDN and from Mouser's mirror, so a person downloads it and `vendor_fetch.py --from-file` ingests it. The nearest real pair is the 82574 (`8086:10d3`), which base's `e1000e` binds | the join, the record format, and the rule that a field is added when a real pair needs it |
| **H9** errata lineage | data | **Six more Intel spec updates**, one per generation, same download problem | `lineage.py`, `retrodict.py`, `erratum-classes.yaml`, `lineage.yaml`, and their tests. All refuse below two documents |
| **H7** generated mitigations | generation | **A VMM in a tree.** F00F needs `vmm_protect` | the mitigation registry, the gates, the pre-registration |
| **F7/F8/F9/F11** service builds | generation | **A model that can write the service.** Each spec, host suite and two-boot acceptance is ready; the run is one command | `run-storage-acceptance.sh --service <name>`, frozen suites, injected-bug scores |
| **D2** aarch64 arch layer | generation | same | the scaffold, the DTB parser, and a smoke test proving the scaffolding boots under HVF |
| **Doom** | decision | **The engine's licence** (`kernel_spec/decisions/doom-engine-licence.md`) blocks *distributing* an image, not building one | the spec, the i8042 decision, the module-asset path |
| **Fleet endpoint** | decision | **Where a report goes, if anywhere** (`decisions/fleet-endpoint.md`) | the allowlist schema, the local aggregator, the consent flow |
| **Proxmox / WSL2 / metal / real silicon** | hardware | machines this project does not have | the harnesses that will run on them, and `CONFORMANCE-HARDWARE.md` saying what emulation cannot answer |

The generation rows share one blocker, and it is measured rather than assumed:
`scripts/model-probe.py` qualifies a model on the four ways local models have failed here, and
`.claude/PRPs/reports/` holds a pre-registered run for each.
