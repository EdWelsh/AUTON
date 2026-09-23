# Pre-registration: the memory manager, on a qualified model

**Written 2026-09-23T12:40:29Z, before the run.** Protocol: `completed/w13-factory-f6-rerun.plan.md`.

Same goal text as the w13 gemma4 run (0 lines); only the model and the turn cap differ.

| | w13 (gemma4) | this run |
|---|---|---|
| Model | ollama/gemma4:latest | **ollama_chat/qwen3.5:27b** (4/4 on the probe) |
| Tool turns | 20 | **60** — 20 ended the F6 run mid-task with working code |
| Budget | 60 min | **5 hours** (`ORCH_TIMEOUT=18000`) |
| Loop | `0f620b3` | `36ab8a4`: compile check before review, designs adopted, work never orphaned by a checkout |
| Goal | `goal.txt`, unchanged | identical |

Gates, in order:

1. `KERNEL_TREE=<ws> tests/kernel/run_mm_test.sh` — exit 2 not generated, exit 1 wrong
2. `KERNEL_TREE=<ws> tests/kernel/run_vmm_test.sh`
3. `make -C <ws> iso` and a QEMU boot printing the exact `[MM] PMM initialized: … total, …
   reserved, … free` line and `[BOOT] OK`
4. Injected bugs from F3's set plus w12's five VMM bugs, on whatever is generated

**Stated in advance**: F6 showed this model can write a service that passes a suite it never
saw. The memory manager is harder — it has boot-order constraints a service does not — and the
prediction is *partial*: an mm.h and a pmm.c that compile, with the VMM's permission-change path
the most likely thing to be missing or wrong. Reported either way.

**A prior failure this run is watched for**: the F6 architect rewrote an unrelated 709-line
header. If that recurs here it is a finding about scope, not about capability.
