# Pre-registration: R1 memory manager, attempt 2, on the faster model

**Written 2026-09-29, before the run.** Protocol: the Generation Experiment Protocol, as amended
for sessions in `docs/GENERATION-QUEUE.md`. Campaign: [`w18-generation-campaign`](../plans/w18-generation-campaign.plan.md), step 1.

| | Attempt 1 (w15) | **Attempt 2 (this)** |
|---|---|---|
| Model | `qwen3.5:27b` | **`qwen3.5:9b`**, 4/4 on `model-probe.py` (2026-09-29, slowest call 617 s) |
| Budget | 1 × 5 h, then killed | **up to 4 sessions × 5 h**, each ending PAUSED and resumed (`w17-run-resume`) |
| Loop | `36ab8a4` | `feat/prd-completion` HEAD at start, recorded in `commit.txt`: pause/resume, per-agent tool boundaries, children killed on cancel |
| Base tree | `kernel-base.sh` (v5) | identical |
| Goal | `goal.txt` | **identical** (`.artifacts/authorship/2026-09-22-generate-mm/goal.txt`) |
| Iterations | 10 | 30 per session |

**Gates, in order** (unchanged):

1. `KERNEL_TREE=<ws> tests/kernel/run_mm_test.sh`: exit 2 means not generated, exit 1 means
   generated wrong.
2. `KERNEL_TREE=<ws> tests/kernel/run_vmm_test.sh`.
3. `make -C <ws> iso` and a QEMU boot printing the exact `[MM] PMM initialized: …` line and
   `[BOOT] OK`.
4. Injected bugs from F3's set plus w12's five VMM bugs, on whatever is generated.

**Stop rules** (campaign): at most two attempts per phase, so this is R1's last. Exit 2 twice
or exit 1 twice means the fallback, which is human-authored and labelled `authorship: human`.
Rule 5 applies: a gate defect found mid-run is fixed, re-scored, and the same output re-graded;
that is not an attempt.

**Predictions, stated in advance.**
- Throughput roughly doubles. At least 3 of the 6 tasks close within four sessions.
- The `boot_mmap_t` defect from attempt 1 (the agent invented the dependency's type) recurs
  unless the architect's `mm.h` is adopted first. The gate's `boot.h` fallback now makes that
  diagnosable.
- `pmm.c` passes `run_mm_test.sh` or fails it with a named assertion. `vmm.c` most likely exits
  2, not reached, or 1 on `vmm_protect`.
- If 9b is fast and wrong (exit 1 on both), that answers Open Question 3 (*is the faster model
  enough?*) in the negative. The campaign then continues on 27b for R2, per its table.

## Amendment, before the run: the model

**Written 2026-09-30, before R1 attempt 2 started.** At the owner's direction the campaign runs
on the largest Qwen that fits this machine's ~42 GB. It is **`ollama_chat/qwen3.5:27b-coding-mxfp8`**
(MLX, 30 GB): the coding-tuned 27B dense model at 8-bit, chosen over the 35B-A3B MoE (3B active)
and over the bf16 builds (55 GB, which do not fit). 9b and 27b (int4) were removed from the
machine at the owner's request.

Everything else above stands: the goal, the gates in order, 4 sessions × 5 h, the stop rules.
This is still R1's attempt 2 (its last); only the model differs, and the report says so.
Qualification with `scripts/model-probe.py` (4/4) is a precondition, recorded before session 1.

**Revised predictions.** At 8-bit and coding-tuned, the model should hold the `mm.md` interface
better than attempt 1's 27b int4: `boot_mmap_t` taken from `boot.h` rather than invented. It is
slower per call than 9b, so throughput stays the risk. Two tasks closed in the first session
would be better than attempt 1's whole run.

Driver: `scripts/generation_run.py` (sessions with `--resume`, then every gate in order,
archived in the run directory's `RESULT.json`).

**Qualification, recorded before session 1** (2026-09-30 15:11Z): `qwen3.5:27b-coding-mxfp8`
passed all four checks. Tool call 28.6 s; fidelity 22.5 s; long prompt 445 s (it quotes the
spec's `boot_mmap_t` signature; 9b took 617 s); second turn 7.3 s. Session 1 started
15:20:09Z. Run directory: `.artifacts/authorship/2026-09-30-r1-mm-attempt2/`.

## Amendment 2, before any development task ran: the model, again

**Written 2026-10-01.** R1 attempt 2 on `qwen3.5:27b-coding-mxfp8` was **aborted during the
design phase, twice.** The system killed it under memory pressure. Under Ollama's MLX engine the
model's context cache grows with the conversation and ignores `num_ctx`: it was 41–42 GB
resident on a 48 GB machine, with swap exhausted. The memory guard (`6381eef`) paused it
cleanly the second time, and the driver was then reaped while it waited. No development task
had started; only architect designs were committed. The run is archived, unscored, at
`.artifacts/authorship/2026-09-30-r1-mm-attempt2-mxfp8-aborted/`.

With the owner's agreement the model is now **`ollama_chat/qwen3.5:27b-q8_0`**: the same 27B at
8-bit, in GGUF under llama.cpp, where `num_ctx` is honoured. At a 32K context it is about 34 GB,
fixed for the run. It is the general model, not the coding fine-tune; there is no 8-bit coding
build in GGUF.

R1 attempt 2 starts **fresh** on it. A resume refuses a model change by design, and this is a
different experiment from the aborted one. Goal, gates, budget (4 × 5 h) and stop rules are
unchanged. Qualification (`model-probe.py`, 4/4) is recorded before session 1. When the
memory guard fires, the driver now also unloads the model while it waits, and its floor is
15% free.

**Qualification on `qwen3.5:27b-q8_0`, recorded before session 1** (2026-10-01): 4/4. Tool call
32.8 s; fidelity 41.1 s (byte-exact); long prompt 602 s; second turn 12.3 s. Loaded at a 32K
context it is **35 GB, bounded** (`ollama ps` reports a context of 32768, which the MLX build
never honoured). Free memory with the model resident: 19%; the guard floor is 15%. The run
directory is `.artifacts/campaign/r1-mm-attempt2/`, driven by `scripts/campaign.py`.

## Amendment 3: the first q8_0 session was not an attempt

**2026-10-01, before the restart.** The first session on `27b-q8_0` (14:45Z–16:04Z) ended with
**0 tasks planned**, so the model was never asked to write code. That makes it a harness failure,
not an attempt, under the same reasoning that voided w11's runs.
- **The manager invented a tool.** It called `create_task` twenty times, and each call was
  refused as unknown.
- **It lost its instructions.** It then read `arch/x86_64` (58K characters) into a 32K-token
  window. Ollama dropped the oldest messages, the task's instructions among them, and the final
  reply was not the JSON array.

It and R8's first session are archived at `.artifacts/campaign-invalid-2026-10-01/`.

**Fixed before the restart:**
- `create_task` is now a real manager tool, so planning is structured calls and the JSON array
  is the fallback.
- A spec longer than 24,000 characters returns its outline, and `read_spec(..., section=...)`
  reads one section.
- With a context window set, a tool result is capped at a fifth of it, with a truncation note.

R1 attempt 2 restarts fresh with the goal, gates and budget unchanged.

## Amendment 4: the restarted run was not an attempt either

**2026-10-02.** The restart on the `create_task` loop planned 8 tasks, then spent all four
sessions in **design**, and development never started. The gates exited 2, 2, 2. Two harness
defects caused it:
1. **Design was checkpointed only as a whole phase.** Each architect design takes hours on this
   model, so every pause landed inside design, and every resume restarted it from the first
   subsystem. The history shows `arch` adopted twice and `mm` never reached. **Fixed:** each
   subsystem is checkpointed once its design is adopted, and a resume skips it.
2. **The Mac slept.** Sessions 3 and 4 spanned 5 h of wall clock and only 83 and 20 minutes of
   awake time; `pmset` shows sleep on battery. **Fixed:** the campaign runs under
   `caffeinate -ims`.

Archived at `.artifacts/campaign-invalid-2026-10-02/`. R1 attempt 2 starts fresh a third time,
with the goal, gates and budget unchanged. The model has now planned twice and designed for
hours, but has not yet been asked to write the memory manager. This attempt is the first that
can measure that.
