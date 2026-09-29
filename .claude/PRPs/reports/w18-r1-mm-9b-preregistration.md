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
