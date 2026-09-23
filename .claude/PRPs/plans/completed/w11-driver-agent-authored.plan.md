# Plan: Agent-Authored Driver (V8)

**Source PRD**: `auton-driver-development.prd.md` — phase V8
**Depends on**: V5 (landed, the control), w9 workspace safety (landed), F6 (the harness)
**Different from F6 in one way that matters**: a driver is ring-0 DMA-capable code with no process
boundary, and the PRD says a synthesized driver reviewed by nobody must not ship.

## Summary

F6 asks whether an agent can write a service. This asks whether it can write the most dangerous
code in the image, and what that costs against V5's human-authored virtio-net.

The security argument in `auton-driver-development.prd.md:57-77` applies with full force here and
changes the acceptance criteria: **passing the gates is necessary and not sufficient.** A driver
that boots is not a verified driver; it is a driver that has not failed yet.

## Evidence

- `.claude/PRPs/reports/w7-driver-virtio-net-report.md` — V5's cost, recorded as this phase's
  control: **113 spec lines, 135 reference lines, 160 test lines, 29 checks**, 6 injected bugs
  caught.
- `.claude/PRPs/reports/w8-driver-virtio-blk-report.md` — V6's, for the same driver family:
  **84 spec lines, 24 new reference lines, 136 test lines, 16 checks**. Two controls, not one, so
  a single outlier does not set the bar.
- `auton-driver-development.prd.md:57-77` — the security table. *"Nobody has ever run this code. A
  synthesized DMA programming error is an arbitrary-write primitive."*
- `auton-driver-development.prd.md:136-151` — the capability boundary: *"A driver written by an
  agent and reviewed by nobody should not ship, and `review: required` is the default for that
  reason."*
- `agent/kernel_spec/drivers/README.md` — the record format the agent must produce, with
  `verification` mandatory and mechanical.
- `agent/tools/driver_strategy.py` — the selector. An agent that writes `strategy: synthesize`
  against an uninventoried document is making the exact error V4 caught in `virtio-net.md`.
- `agent/tools/driver_verify.py` — V9's gate. `status: implemented` with no observed pass is
  refused, so an agent cannot claim success by writing a status line.
- `tests/kernel/virtio_reference/` — the shared ring arithmetic. A driver in the same family
  starts from proved primitives, which is what makes the cost comparison meaningful rather than a
  comparison of who had to write a binary search.

## Patterns to Mirror

- **Two controls, published including the unflattering ratio**: V6's report.
- **Injected-bug testing**: V5 and V6 each injected real DMA bugs and reported which were caught
  first time. The agent's driver gets the same treatment, with the same bugs where they apply.
- **The selector runs first**: V7's Task 1. V5 asserted a strategy and V4 caught it afterwards;
  doing it in the other order is the point of having a selector.

## Tasks

### Task 1: Choose the device, and run the selector first
- **Action**: Name the device, run `driver_strategy.py --device <id>`, and record its answer
  **before** the loop starts.
- **Why**: if the selector refuses, the experiment is about a device nothing can justify driving,
  and that is a different experiment. Candidate: `virtio-console` (`virtio-mmio:3`, `1af4:1043`)
  — same family as V5 and V6 so the controls apply, and genuinely not yet specified.
- **Gotcha**: do not pick a device V5 or V6 already covers. An agent reproducing an existing
  record is measuring retrieval, not authorship.
- **Validate**: the selector's answer is recorded verbatim; the device has no existing record.

### Task 2: Reuse F6's harness
- **Action**: Same cost rows, with driver-specific ones added: reference lines written vs reused,
  and injected bugs caught.
- **Why**: two phases measuring authorship with two harnesses produce two incomparable numbers.
- **Gotcha**: V6's headline finding was that **new reference lines** was the ratio that mattered
  (0.18), not spec lines. The harness must separate written from reused or it will flatter.
- **Validate**: the harness reproduces V5's and V6's recorded rows from their own artifacts.

### Task 3: Run the loop, once
- **Action**: As F6 Task 3 — one run, transcript and diff kept, budget recorded up front.
- **Gotcha**: the agent must produce a **record** as well as a specification, and `driver_spec.py`
  refuses several ways it might get that wrong — prose verification, a cited document nobody can
  produce, `status: implemented` with no mapping. Each refusal is a data point about what agents
  get wrong, which is more useful than the pass/fail.
- **Validate**: every refusal encountered is recorded with the agent's attempt that caused it.

### Task 4: Injected-bug testing, the same bugs
- **Action**: Apply V5's and V6's injected bugs that are applicable to the new driver, plus any
  the device makes possible.
- **Why this and not just the gates**: the gates prove the driver builds and that its own stated
  checks pass. They cannot prove its checks are any good, and V5's and V6's reports both show
  tests that passed for the wrong reason until widened.
- **Gotcha**: if the agent's tests catch fewer injected bugs than V5's did, **that is the
  finding** and the number goes in the report. It is the difference between "an agent can write a
  driver" and "an agent can write a driver anyone should run."
- **Validate**: the caught/injected ratio is published beside V5's 6/6 and V6's 5/5.

### Task 5: `review: required`, and mean it
- **Action**: The resulting record carries `status: specified` at most. It does not become
  `implemented` on the strength of an agent having written it.
- **Why**: the PRD is explicit, and V9's gate already refuses `implemented` with no observed pass.
  This phase must not be the one that argues for an exception.
- **Validate**: the record's status is `specified`; a human review note is recorded or its absence
  is stated.

## Validation

```bash
python agent/tools/driver_strategy.py --device virtio-mmio:3
auton run "Specify and record a virtio-console driver against kernel_spec/subsystems/drivers.md"
python agent/tools/driver_spec.py --validate agent/kernel_spec/drivers/virtio-console.md
python agent/tools/driver_verify.py --target agent/kernel_spec/targets/firecracker.md
scripts/measure_authorship.sh --driver virtio-console
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| A passing gate is read as a safe driver | **H** | Task 4: injected-bug testing, published as a ratio; Task 5 caps the status |
| The agent reproduces V5's record from the tree | **H** | Task 1's gotcha — a device with no existing record |
| The harness flatters by counting reused lines as written | **H** | Task 2's gotcha; V6 found this is the ratio that matters |
| `status: implemented` is argued for | **M** | Task 5; V9's gate already refuses it mechanically |
| The comparison is unfair because V5 had no shared reference | **M** | V6 is the second control, and it did — two controls bracket it |

## Acceptance
- [ ] The device is chosen with no existing record, and the selector's answer recorded first
- [ ] The harness reproduces V5's and V6's rows from their own artifacts
- [ ] One run, transcript kept, every `driver_spec` refusal recorded with what caused it
- [ ] Injected-bug ratio published beside V5's 6/6 and V6's 5/5
- [ ] The record is `status: specified`; no exception is argued for
- [ ] The cost comparison is published whichever way it falls
