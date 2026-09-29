# Plan: Generation Campaign — R1 through R12, in dependency order, each decided by its gate

## Summary
Every R phase of the completion PRD has a spec, a frozen suite scored by injected bugs, and a
command. What none of them has is a *schedule*: R1 ran once, was cut off at five hours, and
stopped. This plan is the operating procedure for the whole ladder — which run goes next, on
which model, with what budget, what counts as done, and what happens on a negative result — so
the PRD's success metric ("services generated and passing their gate: 7 of 7") can be reached
by following it, not by re-deciding at every step.

## User Story
As the operator, I want one ordered campaign with pre-registered stop rules, so that each
generation run is an experiment whose outcome a gate decides, and the ladder keeps moving on a
negative result instead of stalling.

## Problem → Solution
One run done, eleven undone, no rule for model choice, budget, retries or fallback →
a fixed order (R1 → R2 → {R3,R4,R5,R6,R7} and independent {R8,R9} → {R10,R11,R12}), a model
qualification step, a budget in *sessions* (via `w17-run-resume`), a two-attempt cap, and the
human-authored fallback every earlier generation plan already names, labelled in
`authorship.yaml`.

## Metadata
- **Complexity**: Large (operator time), Small (code)
- **Source PRD**: `prds/auton-completion.prd.md`
- **PRD Phase**: R1–R12, and the scenarios C1–C3 they unlock
- **Estimated Files**: 1 CREATE (`docs/CAMPAIGN.md`), reports per run
- **Depends on**: `w17-run-resume` (hard, for R1/R2 — both exceed five hours on this machine)

---

## The order, and why

| Step | Run | Model | Budget | Gate order (pre-registered) | Unblocks |
|---|---|---|---|---|---|
| 0 | qualify | `qwen3.5:9b`, `qwen3.5:27b` | — | `scripts/model-probe.py`, 4/4 required | every run |
| 1 | **R1 mm, attempt 2** | `qwen3.5:9b` | 4 × 5 h sessions | `run_mm_test.sh` → `run_vmm_test.sh` → `[MM]` boot line | R2, R10, R11, R12 |
| 2 | R8 VirtIO console | 9b | 2 sessions | `run_virtio_console_gate_test.sh` (29) | nothing — **runs while R1 is reviewed** |
| 3 | **R2 storage** | the R1 winner | 4 sessions | `run_virtio_blk_test.sh` → `run_fat32_test.sh` → `run-storage-acceptance.sh <ws>` | R3–R7 |
| 4 | R3 file server | winner | 2 | `run_fileserver_test.sh` → `--service fileserver` | — |
| 5 | R6 repo server | winner | 2 | `run_host_repo_test.sh --clone` → `run-intent-probe.sh host-repo` | **C2** |
| 6 | R5 email | winner | 2 | `run_smtp_test.sh` → `--service smtp` | **C3** |
| 7 | R4 KV store | winner | 2 | `run_kvstore_test.sh` → `--service kvstore` | — |
| 8 | R7 SSH | 27b (crypto port) | 3 | `run_ssh_test.sh` (28) | — |
| 9 | R12 Doom | winner | 3 | `run-intent-probe.sh doom` | **C1** (local only until D1) |
| 10 | R11 conformance | winner | 2 | `run_fault_harness_test.sh` tree mode | — |
| 11 | R10 F00F | winner | 1 | the mitigation's `verify` steps 1–2 (step 3 is X3) | — |
| 12 | R9 aarch64 | winner | 3 | `run_dtb_test.sh` tree mode → `[gate: hal]` → `e2e.sh --arch aarch64` | — |

**Why 9b first on R1.** The R1 report's conclusion is that throughput, not capability, bound the
run: 27b closed one task in five hours. 9b qualifies 4/4 at roughly twice the speed. R1 attempt 2
on 9b is the cheapest test of Open Question 3. If 9b's R1 gates fail *as generated wrong*
(exit 1) where 27b's output was closer, attempt 3 is 27b with the same session budget, and that
is pre-registered now, not decided afterwards.

**Why R6 and R5 before R4.** They close validation scenarios C2 and C3; R4 closes none.

**Why R8 runs during R1 review.** It depends on nothing, and the machine is otherwise idle
while a human reads R1's diff.

## Stop rules (pre-registered once, for every run)

1. **At most two attempts per R phase.** Attempt 2 may change model or budget, never the gate.
2. **Exit 2 twice** (not generated) → the phase falls back to human-authored, labelled
   `authorship: human` in `agent/tools/authorship.yaml`, and the ladder continues. Published as a
   negative result.
3. **Exit 1 twice** (generated wrong) → the same fallback, and the report must quote the failing
   assertions. A near miss is data about the model, not a reason for attempt 3.
4. **Exit 0** → injected-bug score against the generated code, beside the human reference, then
   `scripts/measure_authorship.sh`. A pass whose injected-bug score is below the reference's is
   reported as such.
5. **Gate defect found mid-run** (the `tftp_stub` / `boot.h` class): fix the gate, re-score the
   suite against its reference and injected bugs, **re-grade the same output**. This is not an
   attempt.

## Measurements carried by every report
- Sessions, wall-clock per session, turns used, tasks closed / created.
- Scope creep: lines changed outside the goal's subsystems (Open Question 4).
- Whether a test task was produced and ran, and its injected-bug score if it did (Open Question 1).

## Files to Change

| File | Action | Justification |
|---|---|---|
| `docs/CAMPAIGN.md` | CREATE | the table and stop rules above, in the repo, so a reader without `.claude/` can follow it |
| `docs/GENERATION-QUEUE.md` | UPDATE | link to the campaign; add the `--resume` column |
| `.claude/PRPs/reports/w18-<run>-preregistration.md` | CREATE per run | protocol step 1 |
| `.claude/PRPs/reports/w18-<run>-report.md` | CREATE per run | protocol step 6 |
| `agent/tools/authorship.yaml` | UPDATE per run | who wrote what |
| `prds/auton-completion.prd.md` | UPDATE per run | the Depends-on column carries the result |

## NOT Building
- A scheduler that runs the campaign unattended. Each run's model and budget is a pre-registration, which is a human act.
- TLS, IMAP or a wifi driver (the PRD's own exclusions).
- New gates. If a gate is wrong, rule 5 applies.

---

## Step-by-Step Tasks

### Task 1: Write `docs/CAMPAIGN.md`
- **ACTION**: the order table, stop rules and measurements above; link from `GENERATION-QUEUE.md` and `OPEN-WORK.md`.
- **VALIDATE**: `pytest agent/tests/unit/test_doc_links.py` (every markdown link resolves).

### Task 2: Qualify
- **ACTION**: `.venv/bin/python scripts/model-probe.py ollama_chat/qwen3.5:9b` and `…:27b`; record in the R1 pre-registration. A model that no longer passes 4/4 is not used.

### Task 3: R1 attempt 2
- **ACTION**: pre-register (model 9b, 4 sessions, gate order, predictions); workspace from `scripts/kernel-base.sh`; run with `ORCH_TIMEOUT=18000`; `--resume` until complete or four sessions used; grade; report.
- **GOTCHA**: the `boot.h` fallback fixed after attempt 1 is in the gate now; attempt 2 is graded by the fixed gate, and the report says so.

### Tasks 4–14: one per step 2–12 in the table
Each identical in shape: pre-register → run (resuming) → gate in order → injected bugs → authorship → report → PRD row.

### Task 15: Close the scenarios
- **ACTION**: after R6, R5, R12 pass, run `AUTON train` end to end for C2, C3, C1 and record the external probe verdict in the PRD's scenario table.

## Validation Commands
```bash
.venv/bin/python scripts/model-probe.py ollama_chat/qwen3.5:9b
ORCH_TIMEOUT=18000 ORCH_CONFIG=<cfg> scripts/orchestrate-native.sh "$(cat goal.txt)"
scripts/orchestrate-native.sh --resume
KERNEL_TREE=<ws> tests/kernel/run_mm_test.sh; echo $?
scripts/measure_authorship.sh <ws>
```

## Acceptance Criteria
- [ ] Every R phase has a pre-registration and a report, whatever the outcome.
- [ ] Every R phase ends in exactly one of: generated & passing, human fallback (labelled), or blocked on a named X/D phase.
- [ ] C1, C2, C3 each have an external probe verdict recorded.
- [ ] The PRD's "Services generated and passing their gate" row is updated with the real count.

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| 9b is fast and wrong | medium | attempt 2 on 27b is pre-registered; rule 3 stops a third |
| One Mac, weeks of wall-clock | high | R8 during reviews; sessions overnight; the order puts scenario-closing runs first |
| A pass hides a weak agent-written suite | medium | injected-bug score is reported beside the reference, rule 4 |

## Notes
This plan changes no code outside `docs/`. Its output is evidence: twelve reports, and for each
R phase, an answer to "did the agents write it?".
