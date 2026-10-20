# Pre-registration: campaign attempt 3, honest gates from the first iteration (w25)

**Written 2026-10-13, before any run.** A *different experiment* from the 2026-10-10 re-run (w23);
its verdicts stay as recorded. Stop rule: two attempts per run counted from this experiment, then stop.

**What the last attempt showed** (w24 F-2c): R1's gates became honest only at the end of a 25 h run.
Reading its tree with them showed real model bugs: the allocator does not hand out exactly its free
count nor report empty when drained; the VMM does not adopt the boot map, allocates one table where
three are needed, leaks a table after a failed intermediate allocation, and cannot protect inside or
split a 2 MiB page. The swarm never had the chance to see them.

**Change under test:** the swarm sees behaviour through `run_gate` from iteration 1 (host env supplies
`boot_get_info`, HAL stubs and x86_64 arch constants); portable code with inline assembly is named by
file:line (`portable_asm_check.sh`); every run seeds and names its frozen interface (enforced by
`test_suite_interfaces_declared.py`); a dependant never starts on an empty base.

**Hypothesis:** R1's earlier failure was lost feedback, not lack of capability. **Prediction:** with
behavioural failures visible each iteration, R1's `run_mm_test.sh` passes or fails at a *behavioural*
check inside its budget; the VMM's five listed bugs are the first things the reviewers cite.

**Falsified if:** the final tree fails the same behavioural checks after the swarm was shown them
every iteration (then it is model capability, and the next change is a larger model or a decomposed
goal, pre-registered separately); or a compile/link/harness failure returns (then a harness defect,
fix and record, do not count the attempt).

**Order:** R1, then R2, then R3/R4/R5/R6/R7, then R9, then R10/R11/R12. A dependant runs only when its
base run's gates are green (R8 stays passed). **Not predicted:** that all pass. A pass is a result; a
failure at a later gate than before is progress; I will not re-run a run on a changed harness without
a new pre-registration.

## Amendment 2026-10-17, before R1 starts: the host

This experiment runs on a **Linux x86_64 cloud container** (4 cores, 15 GB), not the Mac.

- **Model:** `claude-cli/claude-sonnet-5-5` only, qualified 4/4 here by `scripts/model-probe.py`
  (slowest call 21 s). No Ollama on this host, so the fallback disables itself: a usage limit is
  a wait, never a model switch, and every run is single-model.
- **Gates checked here first** against the references: `run_mm_test.sh --self-test` passes,
  `--inject` 9/9; `run_vmm_test.sh --self-test` passes; `boot-marker.sh` builds and boots
  `kernel-base-v5` in QEMU (TCG). One harness defect was found and fixed before any run:
  `boot-marker.sh` used BSD `mktemp -t`, which fails on GNU and would have scored every boot
  gate "not generated".
- **Different from the Mac:** the host suites compile with x86_64 clang, so inline assembly in
  portable code compiles here; `portable_asm_check.sh` still names it. QEMU runs without KVM.
- **Where kernels go:** every generated tree lives under `.artifacts/campaign/<run>-attempt<k>/ws`
  (gitignored). Nothing generated enters the tracked tree.
- `runs.yaml`: `r1-mm` attempts restart at 1 (dated amendment there). R8's pass stands from the
  Mac and is not re-run.

**Amendment 2026-10-17, before R1 starts: R8 and R1's fallback, as data.** The line above was prose
only, and `scripts/campaign.py` would have run R8 after R1. `runs.yaml` now marks R8
`skip: passed on the Mac (2026-10-10)`, which the campaign honours. R1's fallback
`tree:r1-mm-attempt2` named campaign 2's tree (on the Mac); after the attempt reset it named this
experiment's attempt 2, and the boot gate passes on the untouched base. It is now `none`, and the
campaign takes no fallback tree whose main does not differ from its base.

## Amendment 2026-10-19, before R1 starts: the model, and the host

The owner withdrew the Claude subscription from this work (2026-10-19). **Model:**
`ollama_chat/qwen3-coder:30b`, run locally on the Mac (M4 Pro, 48 GB): Qwen3-Coder-30B-A3B-Instruct,
Ollama's build, 18 GB, a non-thinking mixture of experts with 3B parameters active. Chosen by
searching Hugging Face and then testing, not by reputation. Qualified 4/4 by `scripts/model-probe.py`
(tool call 2.8 s, fidelity 1.3 s, 25k-character spec 24 s, second turn 1.3 s). Context 65,536.
Passed over after measurement: Qwen3.6-35B-A3B (a first R1 started on it and was stopped after 20
minutes and discarded: it thinks 3,000 to 14,000 tokens before a trivial reply, 4-minute calls, and with
thinking off it called no tool on the 26k-character spec, 0 of 3); Laguna XS 2.1 (Ollama 0.40.6
aborts every short prompt with "token repeat limit reached").

**This is a different experiment again.** The model changes from the Claude subscription of the
2026-10-17 amendment, and the host from the Linux container back to the Mac, where host suites
compile with arm64 clang (so `portable_asm_check.sh` and the I/O shim matter). Attempts restart
at 1. Stop rule unchanged (two attempts, then stop). The hypothesis is unchanged: R1's earlier
failures were lost feedback, not capability; a null result on a local model says nothing about
Claude.

The earlier campaign's directory is kept as `.artifacts/campaign-superseded-2026-10-19/`.

**Amendment 2026-10-19 (2 h into R1 attempt 1): context 32,768, not 65,536.** At 65,536 a loop's prompt grew to
about 60k tokens: prompt processing fell from 400 tokens/s (3.5k tokens) to about 120 tokens/s, per-turn latency
climbed from 8 s to 18 s, and each history compaction re-read the window in 8 to 9 minutes (Ollama log,
`prompt eval time` 549 s for 64,462 tokens). The harness's spec truncation and 80% compaction were built for a
32k window. The run was resumed with the same workspace; the change affects speed and what fits in a prompt, not
the goal, gates or stop rule. The work done before the change (tasks mm-001..mm-007 merged) was produced at 65,536.

**Amendment 2026-10-20 (after R1 attempt 1's verdict): the engine's syntax gate and the reviewer's reading of `run_gate` changed.** R1 attempt 1
failed on its merits (see `w25-r1-attempt1-local-report.md`) and counts. Attempt 2 failed in 43 minutes on two harness defects (w24 F-13)
and does not count; it is rerun under the fixed harness. The fix is to the engine's header check (seeded reference headers as a last-resort
include path) and to the reviewer's instructions, not to the goal, the gates or the stop rule. Attempt 1 therefore ran under the old text and
attempt 2 will run under the new one; the report on attempt 2 says so.

