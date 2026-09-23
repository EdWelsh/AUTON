# Plan: V8 Re-run: Agent-Authored Driver (after the loop repair)

## Summary
w11 ran V8 once: 0 lines, the same loop defects as F6 (`w11-driver-agent-authored-report.md`).
The subject stays `virtio-console` (`virtio-mmio:3`, `1af4:1043`), with the selector's answer
already recorded (*synthesize: available, VIRTIO 1.2 ingested*). This plan re-runs it once under
the Generation Experiment Protocol, with the phase's defining step, **injected-bug testing
against V5's 6/6 and V6's 5/5**, done on whatever the agent produces. Passing its own tests is
necessary and not sufficient; the PRD is explicit that a synthesized driver reviewed by nobody
must not ship.

## User Story
As the driver PRD, I want to know whether an agent can write the most dangerous code in the
image, and whether its tests catch the DMA bugs a human's did, so that `synthesize` has a
measured cost and a measured risk.

## Problem → Solution
No measurement → one pre-registered run; a human gate suite written before it; the agent's
spec section, record and host tests measured by `measure_authorship.py`; injected bugs scored;
`status: specified` at most.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `auton-driver-development.prd.md`
- **PRD Phase**: V8
- **Estimated Files**: 3 human (gate) + agent output + report
- **Depends on**: `w12-loop-review-repair` (read_spec reaches `drivers/`), `w12-kernel-base`

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `w13-factory-f6-rerun.plan.md` | protocol | the protocol |
| P0 | `.claude/PRPs/reports/w11-driver-agent-authored-report.md` | all | selector transcript, the control re-count (V5 28 cases, not 29) |
| P0 | `.claude/PRPs/reports/w7-driver-virtio-net-report.md`, `w8-driver-virtio-blk-report.md` | "What the host tests caught" | the injected bug sets |
| P0 | `agent/tools/authorship.yaml` | `virtio-console` | paths the harness measures |
| P1 | VIRTIO 1.2 §5.3 (ingested, `.cache/vendor/oasis-virtio/virtio-spec`) | — | the subject's normative text |

## Patterns to Mirror
### INJECTED_BUGS
// SOURCE: w7 report: 6 injected ring bugs, which were caught first try, which only after better cases.
### STATUS_CAP
// SOURCE: agent/tools/driver_verify.py: `implemented` refused without an observed pass.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `tests/kernel/virtio_console_gate_test.c` + runner | CREATE (human, before the run) | the gate: port-0 receiveq/transmitq chain shapes (§5.3.6), `VIRTIO_CONSOLE_F_SIZE` config read, the device-writable flag on receive buffers; proved against a small reference |
| `agent/tools/authorship.yaml` | UPDATE | `gate_tests` for virtio-console |
| pre-registration + report | CREATE | |

## NOT Building
- Multiport (`VIRTIO_CONSOLE_F_MULTIPORT`). Single port only, stated in the goal.
- Promoting the record past `specified`.

## Step-by-Step Tasks
### Task 1: Human gate suite + reference (frozen before the run)
### Task 2: Pre-register (goal: spec section in `drivers.md`, record `drivers/virtio-console.md`, host tests + runner, reuse `virtio_reference/`)
### Task 3: Run once, archive
### Task 4: Gates: `driver_spec.py --validate` (record) → the human gate suite in tree mode against the agent's reference → the agent's own tests run
### Task 5: Injected bugs into the agent's reference; score the **agent's** tests (caught/injected) beside V5 6/6 and V6 5/5
- **GOTCHA**: score the agent's tests and the human gate suite separately. The question is whether the agent's own verification is any good.
### Task 6: Measure (harness; new vs reused reference lines, the ratio V6 said matters) and report

## Validation Commands
```bash
tests/kernel/run_virtio_console_gate_test.sh --self-test
.venv/bin/python agent/tools/driver_spec.py --validate <ws>/…/virtio-console.md
scripts/measure_authorship.sh --driver virtio-console --root <ws>
scripts/measure_authorship.sh --driver virtio-net && scripts/measure_authorship.sh --driver virtio-blk
```

## Acceptance Criteria
- [ ] One pre-registered run, archived
- [ ] Every `driver_spec` refusal recorded with the attempt that caused it
- [ ] The agent's injected-bug ratio published beside 6/6 and 5/5
- [ ] The record `status: specified` at most

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The agent's tests pass for the wrong reasons | H | H | injected bugs score them, per V5's lesson |
| The agent reproduces virtio-net | M | M | a different device and §5.3; the diff against virtio-net checked |
