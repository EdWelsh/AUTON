# Implementation Report: Elicitation (D5)

## Summary

The last phase of the hardware-definition PRD, built last on purpose. D2 derives a target from an
AUTON host's provenance, D3 from a hypervisor and machine type, D4 reads one off a running
machine. D5 asks about what is left — and the PRD's hypothesis was that what is left is usually
nothing.

**The hypothesis holds.**

| Path | Questions |
|---|---|
| microVM, derived from `hypervisors.yaml` | **0** |
| AUTON-hosted, derived from `PROVENANCE.json` | **0** |
| VM, probed with `lspci`/`cpuinfo`/`dmidecode` | **0** |
| microVM, elicited | 5 |
| VM, elicited, probe accepted | 4 |
| bare metal, elicited, probe accepted | 4 |
| bare metal, elicited, probe refused | 5 |

The PRD named the risk as "elicitation becomes a 40-question form nobody finishes". The worst
path is five questions. A test asserts a ceiling of eight — deliberately far below forty, so
drift is caught long before it becomes the product.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Ask only what is left | Complete | questions come from `missing_facts` |
| 2 | Offer the cheaper path first | Complete | probe before any device question |
| 3 | The container case surfaced, never resolved | Complete | its own question, asked once |
| 4 | Every answer carries `source: user-stated` | Complete | the third leg of the source rule |
| 5 | "I don't know" is an answer | Complete | with one distinction, below |
| 6 | Measure the hypothesis | Complete | `--measure`, table above |

## Task 1: one list, not two

`check_completeness` was refactored to expose `missing_facts(t) -> list[(field, reason)]`, and
now raises from it. Elicitation reads the same list. A second list of questions would drift, and
the drift shows up as either asking for something the format does not need or failing to ask for
something it does. A test asserts the next question always names a field the validator currently
reports as missing.

## Task 5: a distinction the plan did not anticipate

The plan said a declined question leaves the fact unstated. That is right for most fields and
wrong for one.

`unknown` for silicon is not a decline — it is a **statement**: "nobody can know, the host chooses
the CPU". It is exactly the statement D3's derivation makes for a microVM guest, and it is
recorded the same way, as `source: assumed`. Treating it as a decline omitted the field entirely,
which made the target unparseable rather than refused-with-a-reason, and meant a five-question
microVM elicitation could not produce a valid target at all.

So `unknown` is no longer in the declined set, and the silicon branch writes the assumed block.
Declining is saying nothing; asserting unknowability is saying something.

## Three loops found and closed

Building this surfaced three ways the conversation failed to advance — all of which would have
produced exactly the 40-question form the PRD warned about:

**The container answer never advanced.** Surfacing the distinction re-asked `class`, which got the
same container answer, forty times. The disambiguation is now its own question, asked once.

**A multi-field platform gap was one question.** `missing_facts` names them together —
`platform.{hypervisor,machine}` — and the key `"hypervisor,machine"` matched no answer, so both
were recorded as declined. Split into one question per field, which is the stated rule anyway.

**Declining the class kept asking.** After `class` was declined the draft fell back to bare-metal
and asked three more questions about a machine nobody had named. Every remaining question is
per-class — what a microVM needs and what bare metal needs share almost nothing — so the
conversation now ends there.

## Task 3: the container case

```
A kernel cannot run inside a container — a container shares the host's kernel, which is what a
container is. Two things that request can mean, and they produce different artifacts:
  microvm  — a microVM the container runtime schedules (Kata, Firecracker under containerd).
  artifact — an OCI image that ships the ISO for distribution, not execution.
Which do you mean?
```

Neither branch is chosen without an answer. `artifact` sets no class at all and says why — an OCI
image shipping the ISO is a packaging job, not a target definition, because there is no machine
to describe. A parameterised test covers every word in `CONTAINER_WORDS`.

The microVM reading is the more common one, which is exactly why picking it would be the easy
mistake. A test asserts it is not preferred silently.

## One class was unreachable

Checking the PRD's first success metric — *"5 classes, each with a validated definition"* — found
that four of five worked and `k8s-pod` did not. The failure was in elicitation, not the format:
`k8s-pod` contains the substring `k8s`, which is in `CONTAINER_WORDS`, so answering the class
question with the *exact enum value* triggered the container disambiguation. It was the one class
you could not reach by naming it, and the question was offering an option it then refused.

An exact class name is now taken as a choice from the offered list. Prose is still disambiguated —
"run it in a k8s cluster" still produces the question — and a test covers both sides, because
letting exact names through must not open a hole.

All five classes now produce a validated definition:

| Class | Produced by |
|---|---|
| `vm` | `qemu-pc.md`, hand-written; also reproducible by probe |
| `microvm` | `firecracker.md`, hand-written; also derived from `hypervisors.yaml` |
| `auton-hosted` | derived from a host package's `PROVENANCE.json` |
| `bare-metal` | probed from `lspci`/`cpuinfo`/`dmidecode` |
| `k8s-pod` | elicited, 4 questions |

## Validation

1339 unit tests pass (was 1295), 111 SLM tests. 44 new tests. Mutation-tested:

| Mutation | Tests failed |
|---|---|
| container word silently resolved to microvm | 11 |
| probe never offered | 3 |
| accepting the probe still asks for devices | 2 |
| a declined answer filled with a default | 1 |
| elicited devices claim to be `probed` | 2 |
| `unknown` silicon treated as a decline | 5 |
| probe offered after devices instead of before | 1 |
| exact class names intercepted by the container question | 2 |

## Files

| File | Action |
|---|---|
| `agent/tools/elicit.py` | CREATED |
| `agent/tests/unit/test_elicit.py` | CREATED — 36 tests |
| `agent/tools/target_spec.py` | UPDATED — `missing_facts` extracted from `check_completeness` |
| `agent/kernel_spec/targets/README.md` | UPDATED — the elicitation section and the table |

## Acceptance

- [x] Questions come from `check_completeness`'s list, not a second one
- [x] A probe is offered before any device question; accepting removes them
- [x] "Container" surfaces the microVM/artifact distinction and resolves neither
- [x] Every elicited fact carries `source: user-stated`; none says `probed` or `derived`
- [x] A declined question leaves the fact unstated and the target refused naming it
- [x] Question counts per class measured and published above
