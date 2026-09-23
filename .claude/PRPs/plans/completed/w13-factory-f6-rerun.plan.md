# Plan: F6 Re-run: Service #2, Agent-Authored (after the loop repair)

## Summary
w11 ran F6 once and got 0 lines, because the loop could not finish a task chain
(`w11-factory-agent-authored-service-report.md`). With `w12-loop-review-repair` and
`w12-kernel-base` landed, the experiment is finally about the model. This plan re-runs it
**once**, on the same pre-registered subject (`services/tftp.md`), and defines the **Generation
Experiment Protocol** that every w13 generation plan cites.

## User Story
As the project owner testing `README.md:11`, I want one honest measurement of an agent writing
a service against F4's human control, so that "the agents write it" is a number rather than a
claim.

## Problem → Solution
No measurement exists → one pre-registered run, gated by `build_service.py` and the TFTP host
tests, with cost from `measure_authorship.py` beside F4's row, published whichever way it falls.

## Metadata
- **Complexity**: Medium (small code, strict protocol)
- **Source PRD**: `auton-service-kernel-factory.prd.md`
- **PRD Phase**: 6, Service #2, agent-loop authored
- **Estimated Files**: 4 (plus a report and archived artifacts)
- **Depends on**: `w12-loop-review-repair`, `w12-kernel-base`

---

## Generation Experiment Protocol (cited by every w13/w14 generation plan)

1. **Pre-register** in `.claude/PRPs/reports/<plan>-preregistration.md` before the run: subject,
   spec path, goal text verbatim, model and quantisation (`ollama show`), budget (iterations,
   wall clock, $), base (`kernel-base-v5` via `scripts/kernel-base.sh <ws> --git`), and the gates
   that decide.
2. **Spec delivery**: through `read_spec` (w12 widened it). Do not copy specs into the workspace.
   w11 had to, and that is no longer the measured condition.
3. **One run.** `ORCH_TIMEOUT=3600 scripts/orchestrate-native.sh "<goal>"` with
   `[workspace].path` set to the extracted base. No retries, no best-of-N. Budget exhaustion is
   a result.
4. **Archive** under `.artifacts/authorship/<date>-<subject>/`: transcript (plain), task graph,
   per-branch diffs, timing, goal, config. This is w11's layout (`run-exp.sh` in the w11
   pre-registration).
5. **Gates decide**, run by the operator after the loop: the host suite in tree mode
   (`KERNEL_TREE=<ws> tests/kernel/run_<x>_test.sh`), where `exit 2` means not generated and
   `exit 1` means generated wrong; then `build_service.py` / `package_image.py`; then the boot
   markers. Record each result by name.
6. **Injected bugs** into the *generated* code, the same set the reference was proved against.
   Publish caught/injected beside the human control's ratio.
7. **Measure** with `scripts/measure_authorship.sh --<kind> <subject> --root <ws>`. Never hand counts.
8. **Report** both columns and a row for "not caught by anything". A negative result is
   published as plainly as a positive one.

---

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `.claude/PRPs/reports/w11-factory-agent-authored-service-report.md` | all | what failed, the control row, the setup error |
| P0 | `.claude/PRPs/reports/w11-authorship-preregistration.md` | all | the pre-registration format to copy |
| P0 | `agent/kernel_spec/services/tftp.md` | all | the subject: unchanged since pre-registration |
| P0 | `agent/tools/authorship.yaml` | `tftp:` | where the harness looks; update if the loop names files differently, *before* the run |
| P1 | `scripts/orchestrate-native.sh` | 1-60 | the run wrapper and its timeout |
| P1 | `agent/tools/build_service.py` | 256-340 | gate order |

## Patterns to Mirror
### PREREGISTRATION
// SOURCE: .claude/PRPs/reports/w11-authorship-preregistration.md: "Common setup" table + per-experiment block, timestamped, never edited after the run.

### HOST_SUITE_TREE_MODE
// SOURCE: tests/kernel/run_mm_test.sh:28-62. `exit 2` = not generated, `exit 1` = generated wrong.

---

## Files to Change
| File | Action | Justification |
|---|---|---|
| `tests/kernel/tftp_test.c` + `tftp_reference/` + `run_tftp_test.sh` | CREATE | **human-written before the run**: the gate the agent's code must pass, proved `--self-test` against a reference. The agent's own tests are measured separately |
| `.claude/PRPs/reports/w13-factory-f6-rerun-preregistration.md` | CREATE | step 1 |
| `agent/tools/authorship.yaml` | UPDATE | add `gate_tests: tests/kernel/tftp_test.c` so the harness separates human gate tests from agent tests |
| `.claude/PRPs/reports/w13-factory-f6-rerun-report.md` | CREATE | step 8 |

## NOT Building
- Any change to the loop. If the run exposes a new loop defect, that is a finding for a
  follow-up plan, not an in-run patch.
- A second subject. TFTP stays the subject so the pre-registration is comparable.

---

## Step-by-Step Tasks

### Task 1: The human gate suite (before the run)
- **ACTION**: `tftp_test.c` covers `tftp.md`'s 9 acceptance criteria against `tftp_handle`/`tftp_tick`. `tftp_reference/` passes it. `run_tftp_test.sh` follows `run_mm_test.sh`.
- **GOTCHA**: Write it *before* the run and do not change it after. Otherwise the gate is fitted to the output.
- **VALIDATE**: `run_tftp_test.sh --self-test` PASS; 5 injected bugs (duplicate-ACK retransmit, final block not empty at 1024, TID not checked, unterminated filename read, no retry cap) each caught.

### Task 2: Pre-register
- **ACTION**: Protocol step 1. The goal text now says "read the spec with `read_spec services/tftp`".
- **VALIDATE**: the file exists with a UTC timestamp before step 3.

### Task 3: Run once, archive
- **ACTION**: Protocol steps 3–4.
- **VALIDATE**: the artifacts directory is complete even on failure.

### Task 4: Gates, bugs, measurement
- **ACTION**: Protocol steps 5–7: `KERNEL_TREE=<ws> tests/kernel/run_tftp_test.sh`, then `build_service.py tftp --tree <ws> --iso`, then boot to the first marker.
- **VALIDATE**: each gate recorded by name; the harness row printed beside F4's.

### Task 5: Report
- **ACTION**: Protocol step 8. Update the factory PRD row 6.
- **VALIDATE**: the report carries both columns, the injected-bug ratio, and the "not caught" row.

## Validation Commands
```bash
tests/kernel/run_tftp_test.sh --self-test
KERNEL_TREE=<ws> tests/kernel/run_tftp_test.sh
.venv/bin/python agent/tools/build_service.py tftp --tree <ws> --iso
scripts/measure_authorship.sh --service tftp --root <ws>
scripts/measure_authorship.sh --service dhcp
```

## Acceptance Criteria
- [ ] Gate suite written and proved before the run
- [ ] Pre-registered; one run; artifacts archived
- [ ] Gates decide, by name; injected-bug ratio published
- [ ] Report published whichever way it falls

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| gemma4 (8B) cannot write TFTP | H | — | That is the result. A second pre-registered run on a larger model is a separate, stated experiment |
| The gate suite is fitted to the output | M | H | written and frozen before the run (Task 1) |
| The loop exposes a new defect | M | M | recorded; follow-up plan; no in-run fixes |
