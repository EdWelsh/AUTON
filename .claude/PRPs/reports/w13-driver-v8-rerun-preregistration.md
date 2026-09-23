# Pre-registration: V8 re-run (virtio-console, agent-authored)

**Written 2026-09-22T16:45:31Z, before the run.** Protocol: `completed/w13-factory-f6-rerun.plan.md`.

| | |
|---|---|
| Subject | virtio-console, VIRTIO 1.2 §5.3, single port; selector answer *synthesize* (w11) |
| Model | ollama/gemma4:latest, 8.0B, Q4_K_M · $0 · 30 iterations · 60 min · 600 s per call |
| Loop | as of `202db69` (compile check before review; designs adopted) |
| Workspace | kernel-base-v5 + `spec/` copy of agent/kernel_spec + `tests/kernel/virtio_reference/` + virtio_blk_test.c + the frozen interface `virtio_console_gate/include/virtio_console.h`. The gate test is **not** in the workspace |
| Goal | verbatim in `goal.txt`; w11's goal plus deliverable (3), the reference against the frozen interface |
| Gates, in order | `driver_spec.py --validate <ws>/spec/drivers/virtio-console.md`; `KERNEL_TREE=<ws> tests/kernel/run_virtio_console_gate_test.sh` (29 checks, frozen at `242ee08`, 8/8 injected bugs on the human reference); the agent's own runner |
| Scoring | the 8 injected bugs applied to the agent's reference, scored against **the agent's tests** and the gate suite separately, beside V5 6/6 and V6 5/5 |
| Expected | as in F6, generate-mm and storage: little or nothing. Reported either way |
