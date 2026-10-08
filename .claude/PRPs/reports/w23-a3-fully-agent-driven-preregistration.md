# Pre-registration: w23 A3, w22 fully agent-driven on the coding 27b

**Written 2026-10-08, before the run.** Same three pinned subjects, operator-written probes and
exercises as [w22](w22-app-three-runtimes-preregistration.md); `scripts/app_to_env.py`, no
`--record` and no `--recipe`. Only the model changes: `ollama_chat/qwen3.5:27b-coding-mxfp8`,
context 32,768, 2 h per agent stage. w22 on the 9b: 0 of 3 analysed within budget.

**Gate (the PRD headline):** a subject reaching `ablate` with no human record or recipe counts as
fully agent-driven. Target: more than 0 of 3. Each ends at exactly one stage, as in w22.

**Predictions.** The 27b analyses all three (A2 passed on the fixture). Packaging whoami (Go,
scratch) is the most likely failure. Node over-claims libraries, and ablation reports them.

**If A3 is still 0 of 3,** the report says local models on this machine cannot do the analysis,
and the next lever is the prompt and vocabulary, not a larger model.
