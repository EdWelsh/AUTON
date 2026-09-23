# Pre-registration: generate the memory manager (PMM + VMM)

**Written 2026-09-22T12:45:13Z, before the run.** Protocol: `w13-factory-f6-rerun.plan.md`.

| | |
|---|---|
| Subject | `mm.md` PMM (F3) + VMM (w12), into `kernel-base-v5` |
| Model | ollama/gemma4:latest, 8.0B, Q4_K_M |
| Budget | $0; 30 iterations; 60 min; 600 s per call |
| Loop | as of `0f620b3` (tool calls logged; unknown tools name the real ones) |
| Goal | verbatim in `goal.txt` |
| Gates, in order | `KERNEL_TREE=<ws> tests/kernel/run_mm_test.sh`; `run_vmm_test.sh`; `make iso`; boot prints `[MM] PMM initialized: <total> pages total, <reserved> reserved, <free> free` and `[BOOT] OK` |
| Expected, stated | F6 showed gemma4 confuses spec functions with tools; the same failure is likely. Reported either way |
