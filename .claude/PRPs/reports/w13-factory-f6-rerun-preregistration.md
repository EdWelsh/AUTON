# Pre-registration: F6 re-run (service #2, agent-authored)

**Written 2026-09-22T12:35:19Z, before the run.** Not edited after it. Corrections go in the report.

| | |
|---|---|
| Subject | `tftp`, unchanged since the w11 pre-registration (`agent/kernel_spec/services/tftp.md`) |
| Model | `ollama/gemma4:latest`, gemma4 8.0B, Q4_K_M, local |
| Budget | $0; 30 iterations; 60 min wall clock (`ORCH_TIMEOUT=3600`); 600 s per model call |
| Base | `kernel-base-v5` (b0ce7c7) via `scripts/kernel-base.sh <ws> --git` |
| Loop | as of `cfe1818`: the nine w12 fixes (review path, grounded review, timeouts, work stays on its branch) |
| Spec delivery | `read_spec services/tftp`, no copy in the workspace (w11 had to copy; that was a defect, fixed) |
| Run | once: `ORCH_CONFIG=<exp>/auton.toml ORCH_TIMEOUT=3600 scripts/orchestrate-native.sh "<goal>"` |
| Goal | verbatim in `goal.txt` beside the workspace, reproduced in the report |

## Gates, in order, run by the operator after the loop

1. `KERNEL_TREE=<ws> tests/kernel/run_tftp_test.sh`, the human gate suite **frozen at `0fa2589`**
   (31 checks, 5/5 injected bugs caught). exit 2 = not generated, 1 = generated wrong.
2. `build_service.py tftp --tree <ws> --iso`, the factory gates in order (spec, sources,
   capabilities, link closure, hal, build, leakage).
3. Boot to `[TFTP] listening on :69`.

Then injected bugs into the agent's server (the same five), and the agent's **own** tests scored
separately. Then `measure_authorship.sh --service tftp --root <ws>` beside F4's row.

## What counts

- **Worked**: gate 1 passes and the image boots to the first marker.
- **Partial**: the server is present but a gate fails; the report names which.
- **Nothing**: no server file; the report names where the loop stopped.

A negative result is published as plainly as a positive one.
