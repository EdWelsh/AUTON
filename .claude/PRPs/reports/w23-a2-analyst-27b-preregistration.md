# Pre-registration: w23 A2, the fixture Analyst run on the coding 27b

**Written 2026-10-08, before the run.** Same protocol and gate as
[`w18-analyst-live-preregistration`](w18-analyst-live-preregistration.md); the only change is the model.

| | |
|---|---|
| Model | `ollama_chat/qwen3.5:27b-coding-mxfp8`, qualified 4/4 on 2026-10-08 (slowest call 458 s) |
| Subject | `agent/tests/fixtures/apps/flask-hello` |
| Budget | `ORCH_TIMEOUT=14400` (4 h), 10 iterations, 60 tool turns, 3 review rounds, context 32,768 |
| Goal | `Analyse the application staged at .auton/subject/ and write its artifact record.` |
| Prior | 9b, four runs: run 4 merged a record, but over-claimed ("needed because the base has it") |

**Gate.** A record merges, and the reviewer (not only the tool) reads it. No phantom capability
reaches the reviewer. Watch whether the reviewer rejects "needed because the base has it".

**Predictions.** 27b gets runtime and port right and is refused at most twice. It still includes at
least one over-claim a reviewer should catch. If the record merges with no over-claim, C2 (prompt
change) is unnecessary; if it over-claims, C2 is justified by this record.

**Labelled caveat.** The Claude-to-qwen fallback is not involved: the primary model here is local.
