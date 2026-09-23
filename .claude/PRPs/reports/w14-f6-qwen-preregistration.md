# Pre-registration: F6 (TFTP service) on a qualified model

**Written 2026-09-22T19:53:25Z, before the run.** Protocol: `completed/w13-factory-f6-rerun.plan.md`.

The only deliberate difference from the w13 F6 re-run is **the model**. Same goal text, same
base, same frozen gate suite, same repo (plus the loop fixes w13 found).

| | w13 F6 | this run |
|---|---|---|
| Model | ollama/gemma4:latest (3/4 on the probe) | **ollama_chat/qwen3.5:27b (4/4, slowest call 492s)** |
| Goal | `.artifacts/authorship/2026-09-22-f6-rerun/goal.txt` | identical, byte for byte |
| Base | kernel-base-v5 | kernel-base-v5 |
| Gate | `tests/kernel/run_tftp_test.sh` (31 checks, frozen `0fa2589`) | identical |
| Loop | `0f620b3` | `2397416`: compile check and record check before review, designs adopted |
| Budget | 60 min | **4 hours** (one call with a full spec takes ~8 min) |
| Expected | 0 lines (what happened) | **stated in advance: unknown.** The probe says the model can call tools, keep content intact, work from a 25k-char spec, and continue after a tool result. Whether it can write a working service is exactly what this measures |

Gates, in order: `KERNEL_TREE=<ws> tests/kernel/run_tftp_test.sh` (exit 2 not generated, exit 1
wrong); then the injected-bug set on whatever is produced; then
`scripts/measure_authorship.sh --service tftp`.
