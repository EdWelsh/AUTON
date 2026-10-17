# AUTON — working rules

- This repository builds the **agents that create kernels**. It does not hold a generated kernel.
- Any kernel that gets created (generation runs, campaign attempts, e2e builds) belongs in a testing
  or runtime area, never in the tracked source tree:
  - `agent/workspace/` — agent workspaces (gitignored)
  - `.artifacts/` — campaign and e2e output, e.g. `.artifacts/campaign/<run>-attempt<k>/` (gitignored)
  - `tests/kernel/` — frozen suites and the hand-written reference implementations they're scored against
- `agent/kernel_spec/` holds specs and templates the agents read. It is input to generation, not a kernel.
