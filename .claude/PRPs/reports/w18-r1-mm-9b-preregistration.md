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
