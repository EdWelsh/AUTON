# What is Plannable, and What Is Not

Surveyed across all six PRDs **after w11** (2026-09-21). The question it answers: *which
remaining phases can a plan actually produce work for?*

**Superseded by planning (2026-09-21):** the four blockers below now have plans (`w12-loop-review-repair`,
`w12-kernel-base`, `w12-vmm-spec`), and the human decisions are gates inside the plans that need them.
Every remaining phase is planned. See the wave table in [README.md](README.md). This file
stays as the record of *why* w12 comes first.

## What w11 established

| Plan | Outcome | Report |
|---|---|---|
| A2 host-agnostic entry | **complete.** `auton_accel`, `--accel`, `docs/HOST-MATRIX.md`; an x86 guest on Apple Silicon is TCG-only, and a `uname` guess would have picked HVF and failed | `w11-portability-host-agnostic-entry-report.md` |
| intent-G Doom | spec written, input **accepted by recorded decision**, `module-asset` specified. Still blocked: no tree, plus a **new** blocker (doomgeneric is GPL-2.0) | `w11-intent-doom-report.md` |
| F6 agent-authored service | **one run, 0 lines.** The loop died at iteration 1 | `w11-factory-agent-authored-service-report.md` |
| V8 agent-authored driver | **one run, 0 lines.** Same three defects, reproduced | `w11-driver-agent-authored-report.md` |
| H7 generated mitigations | **not runnable.** `vmm` is phantom in every tree | `w11-hardware-generated-mitigations-report.md` |

`README.md:11` (*"the agents do"*) **remains untested.** Both runs failed in the loop's
plumbing before the model was asked to write anything.

## The four blockers, none of which is yet a PRD phase

### 1. The agent loop cannot complete a task chain (blocks F6, V8, H7, and every generation phase)

Found in F6, reproduced in V8, with file:line in the F6 report:

- `base_agent.py:133`: a non-developer task reports `branch = main`.
- `engine.py:343` / `_trigger_review`: an empty diff goes to review, and a local model invents
  code to reject.
- `engine.py:446`: `request_changes` sets `BLOCKED`, which is terminal. The "send feedback to
  developer" comment has nothing behind it.
- The manager emits "read the spec" tasks, which have no deliverable.
- `read_spec` cannot reach `services/`, `drivers/` or `mitigations/`, so no agent can read the
  document it is asked to implement.

This is a **wave-0-class fix**: small, outside every PRD, and it changes the cost of everything
downstream. It is the scheduler-dispatch fix again, one layer up. **Plan it first.**

### 2. No kernel tree exists to generate into (blocks intent-G, F7, V-implementations)

The last tracked tree is `5fb2777^` (F4's base: reference + static-IP `setup.c` + weak
`service_main`). Every experiment needs it, and nothing names it except the w11 reports. Decide
whether it becomes a tagged base (`kernel-base-v2`), or whether the loop is expected to produce
one from nothing. The second is the premise; the first is what makes a *service* experiment
measure a service.

### 3. No VMM (blocks H7, and every page-permission mitigation)

`vmm` and `slab` map to files that have never existed (`kernel/mm/vmm.c`, `slab.c`). The seed
tree identity-maps 4 GiB with 2 MiB pages. F00F needs a read-only 4 KiB page. **Either remove
the phantom mappings, as w8 did for `framebuffer` and `virtio-blk`, or make a VMM a phase.** It
is on the critical path of hardware-truth, not just the factory.

### 4. Decisions only a person can take

| Decision | Blocks | Where it is argued |
|---|---|---|
| **doomgeneric (GPL-2.0) inside a source-available repo's image** | distributing Doom (not specifying or building it) | `services/play-doom.md` *Licence*; `drivers/licences.yaml` routes GPL ports to a human |
| Whether a synthesized driver that passes host tests may be `implemented` without real-hardware runs | V-implementations, the driver PRD's open question 2 | `auton-driver-development.prd.md` *Open Questions* |

## Still blocked on real hardware

Unchanged by w11. `agent/hardware/CONFORMANCE-HARDWARE.md` states the limits.

| Phase | PRD |
|---|---|
| windows-linux 0, A1, A3, B1–B5, C1–C2, D1 | needs a second host and a physical machine. A2 is done, so what those phases need on arrival exists, and `docs/HOST-MATRIX.md` says row by row what has been exercised |
| H10, H10a–e conformance | *"QEMU implements an idealised CPU and will not reproduce silicon divergence"* |
| H12, H13 | hardware-truth |
| intent-J real silicon | intent |

## Still blocked on a data gap

| Phase | The gap |
|---|---|
| V10 errata join | Nothing links a device or a driver to an erratum |
| H9 errata lineage | One errata document is ingested; one document is not a lineage |

## Housekeeping that should precede any new measurement

- **Commit w6–w10.** V5–V7's host references and tests are untracked. V8's harness could not
  reproduce V5's reference split because no version of it was ever committed. A control that
  lives only in a working tree cannot be re-measured.
- **`measure_authorship.py` is the meter.** Of four controls, none reproduced completely from
  its artifacts (F4: tests 255 not 200, implementation 401 not 372; V5: 28 cases not 29; H6 had
  no row). Record new controls through the harness, not by hand.

## What `completed/` means

Every phase done, with a report. Two PRDs qualify:

- `completed/auton-e2e-train-boot-human-test.prd.md` (12 of 12)
- `completed/auton-hardware-definition.prd.md` (8 of 8)

A PRD moved there on the strength of being *planned* or *attempted* would claim work that has
not happened. F6 and V8 were **run**. That is not the same as **done**, and their PRD rows say
so.
