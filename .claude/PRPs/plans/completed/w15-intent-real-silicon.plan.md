# Plan: I6 Real Silicon: Driver Selection on Unseen Hardware (intent-J)

## Summary
I6's sentence is *"my laptop won't connect to wifi, fix it"*, probed by *"correct driver for
real silicon; association succeeds"* (`auton-intent-to-os-compiler.prd.md:205, 250`). It splits
into two claims of very different size:

1. **Selection.** Given a real machine's probe, AUTON names the right driver for each device, or
   honestly refuses. That is reachable now: the device table (intent-I), `probe_ingest` (D4),
   `driver_strategy` (V4) and the PRD's rubric (*honestly refused* is an acceptable grade).
2. **Association.** A working wifi driver: firmware loading, an 802.11 MAC layer, WPA2. That is
   a PRD-sized effort with no spec in this repo, and this plan does not pretend otherwise.

This plan delivers (1) against a corpus of **real captured probes** that were never used to
build the table, and records (2) as the next PRD's scope.

## User Story
As a user with a machine AUTON has never seen, I want to be told truthfully which of my devices
it can drive and which it cannot, so that I never get an image that claims a driver it lacks.

## Problem → Solution
Selection has only been exercised on synthetic targets (`qemu-pc`, `firecracker`) → a
`probes/` corpus of real `lspci -nn`/cpuinfo/dmidecode captures (CI runners, contributors), an
evaluation that runs selection on each and scores it against hand-labelled truth, and a phantom-
driver rate that must be zero.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `auton-intent-to-os-compiler.prd.md`
- **PRD Phase**: J, I6 real silicon (selection half)
- **Estimated Files**: 6

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/tools/probe_ingest.py` | 1-20, 89-120, 194-250 | `parse_lspci`, `probe`, `to_target` |
| P0 | `agent/tools/device_drivers.py` | all | `PCI_DEVICE_DRIVERS`, `DRIVER_CAPS`: the selection table |
| P0 | `agent/tools/driver_strategy.py` | 233-285 | `select`, its refusal |
| P0 | `.claude/PRPs/reports/w10-intent-device-table-report.md` | all | the 5-phantoms-per-50 baseline and target-scoped tables |
| P1 | `agent/tests/unit/test_probe_ingest.py` | all | fixture style for captured text |

## Patterns to Mirror
### CAPTURED_FIXTURE
// SOURCE: agent/tests/unit/test_probe_ingest.py: real command output as fixture text, parsed by `probe_ingest`.
### THREE_WAY_GRADE
// SOURCE: auton-intent-to-os-compiler.prd.md:211-215: worked / honestly refused / failed, where failed includes claiming success.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/hardware/probes/<name>/{lspci.txt,cpuinfo.txt,dmidecode.txt,truth.yaml}` | CREATE | real captures; `truth.yaml` hand-labels each device's correct driver or `none-in-tree` |
| `.github/workflows/portability.yml` | UPDATE | a job step that captures `lspci -nn` + cpuinfo from the x86 runner into an artifact, a free real machine per run |
| `agent/tools/eval_selection.py` | CREATE | per probe: `probe_ingest` → target → per-device selection → graded against truth |
| `agent/tests/unit/test_eval_selection.py` | CREATE | grading logic; a phantom (claiming a driver for an unmapped device) is `failed` |
| `agent/kernel_spec/drivers/README.md` | UPDATE | "what a refusal says to a user": the exact chat phrasing for an undrivable device |
| `.claude/PRPs/prds/` | NOTE | the association half recorded as the next PRD's item (a wifi PRD) |

## NOT Building
- Any wifi driver, firmware loader, or 802.11 stack.
- Selection by model inference. Selection stays a table lookup with provenance (V3's rule).

## Step-by-Step Tasks
### Task 1: A real-probe corpus
- **ACTION**: 3+ probes: the GitHub x86 runner (from the CI artifact), a QEMU `q35` guest (a control with known truth), and any contributor laptop (the owner's, if willing).
- **GOTCHA**: `dmidecode` output contains serial numbers and UUIDs. `probe_ingest` must redact them before anything is committed. Add the redaction if it is missing, with a test.
- **VALIDATE**: every probe parses with zero `unparsed` lines, or the unparsed lines are listed.

### Task 2: Truth labels
- **ACTION**: For each device, the correct in-tree driver or `none-in-tree`, with a one-line reason. Labelled by a person, before running the evaluator.

### Task 3: The evaluator
- **IMPLEMENT**: `eval_selection.py --probes agent/hardware/probes` prints per device: truth, chosen, grade; totals; the phantom count.
- **VALIDATE**: phantom count 0; every `none-in-tree` device graded `honestly refused`.

### Task 4: The user-facing refusal
- **ACTION**: specify the chat answer for "fix my wifi" on a machine whose wifi chip is `none-in-tree`: name the chip (from the registry), say no driver exists, and cite the record or the missing strategy. Never suggest a nearby driver.

## Validation Commands
```bash
.venv/bin/python agent/tools/eval_selection.py --probes agent/hardware/probes
cd agent && ../.venv/bin/python -m pytest tests/unit/test_eval_selection.py tests/unit/test_probe_ingest.py -q
```

## Acceptance Criteria
- [ ] ≥3 real probes with truth labels
- [ ] Phantom-driver rate 0 across the corpus
- [ ] Wifi on unseen silicon is graded **honestly refused**, with the chip named
- [ ] The association half recorded as the next PRD's scope, not silently dropped

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Probes leak identifiers | M | H | redaction with a test; review before commit |
| Truth labels are wrong | M | M | a reason per label; re-labelled when a driver lands |


---

## Closed 2026-09-23

Blocked on an x86 machine. The conformance harness, its oracle and the disclosure path are built and tested.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
