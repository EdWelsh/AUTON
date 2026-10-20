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

The gates that decide each run are the ones in [`campaign/runs.yaml`](campaign/runs.yaml);
where this table differs, `runs.yaml` holds. In particular `run_virtio_blk_test.sh` is
recorded for R2 as advisory, not deciding, and R8 is skipped in w25 attempt 3 (its 2026-10-10
pass stands).

**Model (amended 2026-10-19, owner's decision).** No Claude subscription. Every run uses **`ollama_chat/qwen3-coder:30b`** locally (Qwen3-Coder-30B-A3B-Instruct, 18 GB, a non-thinking mixture of experts with 3B active; context 65,536), qualified 4/4 by `scripts/model-probe.py` (slowest call 24 s). Found by searching Hugging Face and then measuring: Qwen3.6-35B-A3B thinks 3,000 to 14,000 tokens before a trivial reply and calls no tool without thinking; Laguna XS 2.1 aborts every short prompt under Ollama 0.40.6. Attempts restart at 1 (`reports/w25-campaign-attempt3-preregistration.md`, amendment 2026-10-19). R13 (the `cpu` subsystem) is added, independent of R1.

**Model (superseded 2026-10-19; amended 2026-10-02, owner's decision).** Every run uses **Claude Sonnet 5.5 through the owner's Claude subscription** (`claude-cli/claude-sonnet-5-5`: `claude -p` as a pure model, every Claude Code tool disabled, the orchestrator's own tools, sandbox and gates unchanged). Qualified 4/4, slowest call 21 s against qwen q8_0's 602 s. The rows above that name a qwen model are superseded by this line. The q8_0 R1 run was abandoned at the owner's request, unscored.

**Model (amended 2026-09-30).** Every run uses `qwen3.5:27b-q8_0`; the reasoning below is kept for the record. **Why 9b first (superseded).** R1 attempt 1 on 27b closed one task of six in five hours. Throughput, not
capability, was the binding constraint. 9b qualifies 4/4 at about twice the speed. If 9b's
output is *generated wrong* where 27b's was closer, R2 onward runs on 27b.

**Why R6 and R5 before R4.** They close validation scenarios C2 and C3; R4 closes none.

## Budget counts work (amended 2026-10-03)

A run's budget is `sessions × 5 h` of **work**: each session's wall clock less the time it spent
waiting on the model provider's usage limits, which `claude_cli` logs and `generation_run.py`
reads back. That's the same principle as the memory guard: a pause for the host's reasons, or
the provider's, isn't the run's budget spent. Without it, R2's first 5-hour session held 15
minutes of work.

Each `RESULT.json` reports `work_seconds` and `limit_wait_seconds`. Sessions are capped at six
times the pre-registered count, so a provider that never allows work still ends the run.

R1 isn't affected: it ended terminal, with every task merged, after about 30 minutes of work.

## Fallback trees (amended 2026-10-06)

Stop rules 2 and 3 replace a failed phase so its dependants test what their goals assume
exists. `runs.yaml` had `fallback: none` everywhere. R3's goal says to serve files "through the
existing fs API in kernel/include/fs.h", but it ran on `kernel-base-v5`, which has no such file,
so neither R3 attempt tested what was pre-registered. Both are void.

A failed phase whose **end-to-end gate passed** is now its dependants' base, labelled in their
`RESULT.json`:

| Phase | Fallback tree | Evidence |
|---|---|---|
| R1 | `r1-mm-attempt2` | boots: `[MM] PMM initialized: 65504 pages total…`; fails the mm/vmm interface suites |
| R2 | `r2-storage-attempt2` | storage acceptance passes (mount, read, write, host read-back); fails the FAT32 interface suite |

**Amended 2026-10-17 (w25 attempt 3):** R1's fallback is now `none`. `r1-mm-attempt2` named
campaign 2's tree, which is on the Mac; with attempts restarted the name meant this
experiment's own unjudged attempt 2. `scripts/campaign.py` also takes a fallback tree only if
that attempt generated something and its tree differs from the one it started on. R2 still
names `r2-storage-attempt2`.

**This departs from the rule's "human-authored" fallback:** these trees are agent-written. That
is stated here and in each dependant's report. R2's own attempts ran on `kernel-base-v5`, as its
goal (`dma_alloc` from `phys.h`) assumed, and stand.

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

## Every run is observable (amended 2026-10-20)

From the run after this amendment lands, each run directory holds `events.jsonl`: one JSON line
per model call (agent, tokens, seconds, finish reason, tools asked for), tool call (name, seconds,
result size), task start and result, review (who, verdict, why), merge and pause. The orchestrator
writes it when `generation_run.py` sets `AUTON_EVENTS`; unset, nothing is written. It observes and
never decides, so a failure to write cannot change a run.

    .venv/bin/python scripts/run-status.py .artifacts/campaign/<run>      # live or finished
    .venv/bin/python scripts/run-status.py .artifacts/campaign/<run> --json

It shows the task in flight, seconds since the last event (a stall), each agent's tokens and
speed, tools over 60 s, and every task's starts, review verdicts and state. A run's report cites
these numbers rather than reconstructing them from the transcript. The change adds events only:
no prompt, tool, gate or limit changes, so it does not alter what is being measured.

## What every report carries

Sessions and wall-clock per session; turns used; tasks closed of tasks created; lines changed
outside the goal's subsystems (scope creep); and whether a test task was produced and ran, with
its injected-bug score if it did.

## Status

| Run | State | Report |
|---|---|---|
| *Campaign 1* | the rows below | |
| R1 attempt 1 | cut off at 5 h: mm exit 1, vmm exit 2 | [w15-mm-qwen](../.claude/PRPs/reports/w15-mm-qwen-report.md) |
| R1 attempt 2 | **generated wrong (1, 1, 0)**: all 6 tasks merged, boots with a working PMM; suites fail on an inline `phys_to_virt` and x86 asm in portable code. Phase failed (rule 3) | [report](../.claude/PRPs/reports/w18-r1-mm-report.md) |
| R8 VirtIO console | **PASSED** (0) on 2026-10-10, campaign 2 (listed here with the campaign-1 rows it ran beside): one 575 s session | `.artifacts/campaign/r8-virtio-console-attempt1` |
| R2 storage | **generated wrong**: attempt 2 passes storage acceptance end to end; both fail the FAT32 interface suite. Phase failed | [report](../.claude/PRPs/reports/w18-r2-storage-report.md) |
| R3 file server | attempt 1: generated wrong (1, 2); attempt 2 also ran. Both **void**: they ran on `kernel-base-v5`, which has no `fs.h` (see Fallback trees) | — |
| R4–R7, R9–R12 | not run in campaign 1 | — |
| *Campaign 2 (2026-10-10)* | **1 of 12 passed** (R8). The other eleven failed their gates, mostly at suite compile (R1–R6, R9, R11); R7 was not generated; R10's marker was absent; R12's image never built. Every failure investigated | [w24](../.claude/PRPs/plans/w24-campaign-failure-investigations.plan.md) |
| R1 attempt 3 (2026-10-17) | started on a Linux x86_64 host, **stopped by the owner** before a result; not counted | [pre-registration](../.claude/PRPs/reports/w25-campaign-attempt3-preregistration.md) |

**Before the next run:** the example config now enables the 24 specialist agents
(`agents.specialists`), so the next attempt is a different experiment from campaign 2 and
needs a pre-registration that says so. Every run's tree stays in
`.artifacts/campaign/<run>-attempt<k>/ws`, never in the tracked source.

**The campaign as data:** [`campaign/runs.yaml`](campaign/runs.yaml) and [`campaign/goals/`](campaign/goals/) — every run's goal, base, seeds and gates, committed before any of them started. `scripts/campaign.py` runs them in order unattended (dependencies on the last good tree, two attempts, resumable). All runs are driven by `scripts/generation_run.py`: sessions with `--resume` from a pinned wrapper, then every gate in its pre-registered order, archived in the run's `RESULT.json`.
