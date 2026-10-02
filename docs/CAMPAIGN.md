# The generation campaign

The order in which the completion PRD's twelve generation runs (R1–R12) are run, on which model,
with what budget, and what happens on a negative result. Every row is a pre-registered
experiment decided by a frozen gate. The mechanics of one run are in
[`GENERATION-QUEUE.md`](GENERATION-QUEUE.md); this file is the schedule.
Plan: [`w18-generation-campaign`](../.claude/PRPs/plans/w18-generation-campaign.plan.md).

## Order

| Step | Run | Model | Budget | Gates, in order | Unblocks |
|---|---|---|---|---|---|
| 0 | qualify | `qwen3.5:27b-q8_0` (27B at 8-bit, GGUF: its context is bounded; the MLX coding build grew to 42 GB and was retired 2026-10-01) | — | `scripts/model-probe.py`, 4/4 required | every run |
| 1 | **R1 memory manager, attempt 2** | 27b-q8_0 | 4 × 5 h sessions | `run_mm_test.sh` → `run_vmm_test.sh` → `[MM]` boot line | R2, R10, R11, R12 |
| 2 | R8 VirtIO console | 27b-q8_0 | 2 sessions | `run_virtio_console_gate_test.sh` (29) | — (runs while R1 is reviewed) |
| 3 | **R2 storage** | R1's winner | 4 sessions | `run_virtio_blk_test.sh` → `run_fat32_test.sh` → `run-storage-acceptance.sh` | R3–R7 |
| 4 | R3 file server | winner | 2 | `run_fileserver_test.sh` → `--service fileserver` | — |
| 5 | R6 repo server | winner | 2 | `run_host_repo_test.sh --clone` → `run-intent-probe.sh host-repo` | scenario C2 |
| 6 | R5 email | winner | 2 | `run_smtp_test.sh` → `--service smtp` | scenario C3 |
| 7 | R4 KV store | winner | 2 | `run_kvstore_test.sh` → `--service kvstore` | — |
| 8 | R7 SSH | 27b | 3 | `run_ssh_test.sh` (28) | — |
| 9 | R12 Doom (the 1993 original: shareware `DOOM1.WAD` v1.9) | winner | 3 | `run_play_doom_test.sh` → build + leakage → `run-intent-probe.sh doom` | scenario C1 (local only until the licence decision) |
| 10 | R11 conformance | winner | 2 | `run_fault_harness_test.sh` tree mode | — |
| 11 | R10 F00F | winner | 1 | the mitigation's `verify`, steps 1–2 (step 3 needs a family-5 Pentium) | — |
| 12 | R9 aarch64 | winner | 3 | `run_dtb_test.sh` tree mode → `[gate: hal]` → `e2e.sh --arch aarch64` | — |

**Model (amended 2026-10-02, owner's decision).** Every run uses **Claude Sonnet 5.5 through the owner's Claude subscription** (`claude-cli/claude-sonnet-5-5`: `claude -p` as a pure model, every Claude Code tool disabled, the orchestrator's own tools, sandbox and gates unchanged). Qualified 4/4, slowest call 21 s against qwen q8_0's 602 s. The rows above that name a qwen model are superseded by this line. The q8_0 R1 run was abandoned at the owner's request, unscored.

**Model (amended 2026-09-30).** Every run uses `qwen3.5:27b-q8_0`; the reasoning below is kept for the record. **Why 9b first (superseded).** R1 attempt 1 on 27b closed one task of six in five hours. Throughput, not
capability, was the binding constraint. 9b qualifies 4/4 at about twice the speed. If 9b's
output is *generated wrong* where 27b's was closer, R2 onward runs on 27b.

**Why R6 and R5 before R4.** They close validation scenarios C2 and C3; R4 closes none.

## Stop rules, the same for every run

1. **At most two attempts per R phase.** Attempt 2 may change the model or the budget, never the
   gate.
2. **Exit 2 twice** (not generated): the phase falls back to human-authored code, labelled
   `authorship: human` in `agent/tools/authorship.yaml`, and the ladder continues. Published as
   a negative result.
3. **Exit 1 twice** (generated wrong): the same fallback, and the report quotes the failing
   assertions.
4. **Exit 0**: injected-bug score against the generated code, beside the human reference, then
   `scripts/measure_authorship.sh`.
5. **A gate defect found mid-run** (the `tftp_stub` / `boot.h` class): fix the gate, re-score it
   against its reference and injected bugs, and re-grade the same output. This is not an
   attempt.

## What every report carries

Sessions and wall-clock per session; turns used; tasks closed of tasks created; lines changed
outside the goal's subsystems (scope creep); and whether a test task was produced and ran, with
its injected-bug score if it did.

## Status

| Run | State | Report |
|---|---|---|
| R1 attempt 1 | cut off at 5 h: mm exit 1, vmm exit 2 | [w15-mm-qwen](../.claude/PRPs/reports/w15-mm-qwen-report.md) |
| R1 attempt 2 | pre-registered | [preregistration](../.claude/PRPs/reports/w18-r1-mm-9b-preregistration.md) |
| R2–R12 | queued, in the order above | — |

**The campaign as data:** [`campaign/runs.yaml`](campaign/runs.yaml) and [`campaign/goals/`](campaign/goals/) — every run's goal, base, seeds and gates, committed before any of them started. `scripts/campaign.py` runs them in order unattended (dependencies on the last good tree, two attempts, resumable). All runs are driven by `scripts/generation_run.py`: sessions with `--resume` from a pinned wrapper, then every gate in its pre-registered order, archived in the run's `RESULT.json`.
