# Plan: Graded Chat Eval — Phase 6

**Source PRD**: `.claude/PRPs/prds/auton-e2e-train-boot-human-test.prd.md`
**Selected Milestone**: Phase 6 — Graded chat eval
**Complexity**: Medium — and the gate that makes rung 3b meaningful

## Summary

Produce a number that moves when the model changes: 50 prompts across the six intent classes
plus out-of-domain, a three-bucket rubric, a runner that boots the VM and scores, and two
recorded baselines (rule engine, and the rung-3a neural model). Blocks Phase 3b by design.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Intent taxonomy | `kernel/include/slm.h:12-18` | The six `slm_intent_t` classes — the eval's coverage spine |
| Honest-answer convention | `kernel/slm/roles.c:20-40` | `CAP_ROADMAP` + a note saying what's missing = a *correct* answer, not a failure |
| Structured expectations | `agent/kernel_spec/tests/acceptance_tests.py:23,34+` | Dataclass with a pattern list — mirror for prompt/expectation records |
| Serial driving | `scripts/run-acceptance.sh:56-60` | Background QEMU, leading blank line for the dropped first byte |
| Scoring output | `scripts/run-acceptance.sh:95-101` | `PASS`/`FAIL` lines then a terminal verdict |
| Report format | `.claude/PRPs/reports/*-report.md` | Summary then "Assessment vs Reality" table |

## Files to Change

| File | Action | Why |
|---|---|---|
| `tests/eval/prompts.jsonl` | CREATE | 50 prompts, each tagged with intent class and expected bucket |
| `tests/eval/rubric.md` | CREATE | The three buckets, defined precisely enough to grade consistently |
| `scripts/eval.sh` | CREATE | Boot, send all prompts, score, emit JSON + a summary |
| `.claude/PRPs/reports/e2e-eval-baselines.md` | CREATE | Rule-engine and rung-3a baselines |

## Tasks

### Task 1: Define the rubric precisely
- **Action**: Three buckets. **Correct** — factually right for this machine. **Honest
  roadmap** — accurately says it can't do that and why (the `CAP_ROADMAP` convention; this
  counts as success, and that choice is the rubric's most important design decision).
  **Garbage** — wrong, incoherent, or hallucinated. Write enough detail that two gradings a
  week apart agree.
- **Validate**: hand-grade 10 prompts twice, days apart; disagreement on ≤1.

### Task 2: Build the prompt set
- **Action**: 50 prompts spanning all six intent classes plus deliberate out-of-domain
  ("what's the weather"), where the correct answer is an honest refusal. Include real
  phrasing variety — the point is free-form human input, not canned commands.
- **Constraint**: these prompts and the rung-3b training corpus must be **disjoint**
  (asserted from the 3b side). Fix the eval set before 3b's corpus is built.
- **Validate**: all six classes covered; disjointness assertable.

### Task 3: The scoring runner
- **Action**: `scripts/eval.sh` boots the VM, sends each prompt over serial, captures the
  answer, and scores. Fully automatic grading is unrealistic for the "correct vs garbage"
  distinction — support **expected-substring auto-grading where the answer is deterministic**
  (ip, memory, device list, role status) and a human-review queue for the rest, with the
  verdicts cached so a re-run of an unchanged model doesn't re-ask.
- **Mirror**: `run-acceptance.sh:56-78` background-QEMU + probe loop; leading blank line.
- **Validate**: re-running an unchanged model reproduces its score within noise.

### Task 4: Record two baselines
- **Action**: Score the rule engine and the rung-3a neural model. These are the reference
  points 3b and 3c are compared against.
- **Mirror**: report format above.
- **Validate**: both baselines committed with the exact model manifest they describe.

### Task 5: Wire in as an e2e stage
- **Action**: Optional stage `[7/7]` in `scripts/e2e.sh`, reporting correct/honest/garbage
  percentages.
- **Validate**: `scripts/e2e.sh --rung 3a` ends with an eval line.

## Validation

```bash
scripts/eval.sh --model rule                 # rule-engine baseline
scripts/eval.sh --model SLM/work/auton-slm.bin
scripts/eval.sh --model SLM/work/auton-slm.bin   # rerun: score within noise
scripts/e2e.sh --rung 3a                     # eval reported as the final stage
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Auto-grading can't judge free-form answers | **H** | Hybrid by design: substrings where deterministic, cached human verdicts elsewhere. Do not fake full automation |
| Eval set leaks into training data | **H** if unguarded | Fix the eval set *before* 3b builds its corpus; disjointness asserted by a test |
| Rubric drifts between gradings | **M** | Task 1's two-pass self-consistency check |
| 50 prompts × boot time is slow | **M** | One boot, all prompts over the same serial session; only re-boot on model change |
| Score becomes a target and gets gamed | **M** | Phase 7's unscripted human sessions exist precisely to catch this; new findings become new prompts |

## Acceptance
- [ ] Rubric written; two gradings agree on ≥9/10
- [ ] 50 prompts covering six intent classes plus out-of-domain
- [ ] Runner scores automatically where deterministic, queues the rest, caches verdicts
- [ ] Rule-engine and rung-3a baselines recorded with their manifests
- [ ] Unchanged model reproduces its score within noise
- [ ] Eval reported as an `e2e.sh` stage
