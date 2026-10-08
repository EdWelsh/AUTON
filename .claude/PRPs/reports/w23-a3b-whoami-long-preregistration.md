# Pre-registration: w23 A3b, whoami with a 4 h analyst budget

**Written 2026-10-08, before the run.** A *different experiment* from A3 (budget doubled), labelled
as one. Same model (`qwen3.5:27b-coding-mxfp8`), subject, probe and exercise as
[A3](w23-a3-fully-agent-driven-preregistration.md); only `--timeout 14400`.

**Question:** was whoami's A3 failure budget or capability? **Gate:** a merged record and a pass
through `ablate` with no human input.
**Prediction:** the Analyst merges a record in 2–4 h; the Packager (Go multi-stage into scratch)
is where it then fails. A second timeout would mean the model cannot analyse a Go repository in
this setup.
