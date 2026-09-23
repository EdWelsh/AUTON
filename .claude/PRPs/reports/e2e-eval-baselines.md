# Graded Chat Eval — Baselines

**Phase**: 6 — Graded chat eval
**Recorded**: 2026-09-11
**Rubric**: `tests/eval/rubric.md` · **Prompts**: `tests/eval/prompts.jsonl` (50)
**Runner**: `scripts/eval.sh` · **Raw**: `tests/eval/baseline-*.json`

## Summary

Two reference scores, on identical hardware (`-m 256M`), 50 prompts across the six
`slm_intent_t` classes plus out-of-domain.

| Backend | Correct | Honest-roadmap | **Correct-or-honest** | **Garbage** | Bar |
|---|---|---|---|---|---|
| Rule engine | 19 (38%) | 14 (28%) | **66%** | **34%** | FAIL |
| Rung-3a neural | 15 (30%) | 6 (12%) | **42%** | **58%** | FAIL |

**The rung-3a model is substantially worse than the rule engine it replaces.** That is the
expected result and the useful one: 3a trains a 14M-parameter model to memorise a 12-record,
1.7 KB corpus, and it was never meant to hold a conversation. The number moving 66 → 42 is
the eval doing its job — it discriminates between models, which is the whole point of
building it before 3b.

Neither backend clears the bar (≥70% correct-or-honest, <10% garbage). Phase 3b has to move
the neural line from 42% to 70%+ and cut garbage from 58% to under 10%.

## Model identity

| Backend | Fingerprint | Artifact |
|---|---|---|
| Rule engine | `rule:b43d1afed81391dd` | `kernel.bin` at commit `f1a0c9c` |
| Rung-3a neural | `neural:b74e908d9cdfe4af` | `SLM/work/auton-slm.bin`, sha256 `b74e908d9cdfe4af6a280ab0e2a257b43a87e40faff0e7c3ba3bc18d81eb66e5` |

The neural fingerprint matches the rung-3a baseline exactly
(`.claude/PRPs/reports/e2e-rung3a-baseline.md`), so these scores describe that model and no
other. A changed model gets a new fingerprint and re-queues every free-form answer.

## What each backend fails at

### Rule engine — 34% garbage, all of it keyword mismatch

It answers canonical phrasings well and degrades on anything else, because matching is
substring-based and routes to the wrong handler:

| Prompt | Answer | Why garbage |
|---|---|---|
| `what driver is loaded right now` | `Name the device, e.g. 'driver for 8086:100e'` | It knows e1000 is loaded |
| `did you get an address from dhcp` | `Role 'DHCP server': roadmap …` | Client lease vs serving leases — wrong handler |
| `how much ram is free` | `Memory: 255 MB RAM` | Total, not free |
| `why is the network down` | `Plan: identify NIC -> load e1000 -> dhcp` | Network is up; premise not challenged |
| `what is my gateway address` | generic fallback | Known (10.0.2.2), reported inside the IP answer |

It scores well on out-of-domain (all 5 honest) because its generic fallback happens to be an
accurate self-description — accidentally right, but right.

### Rung-3a neural — 58% garbage, mostly degenerate generation

| Prompt | Answer |
|---|---|
| `what is the weather today` | `<unk> <unk> <unk> <unk> …` |
| `tell me about the network card in this machine` | `machine machine machine machine …` |
| `who are you` | `you you you you …` |
| `what is pci 8086:100e` | `identify device 1af4:1000 which driver for the network card what driver do` |

The last one matters: `1af4:1000` is **not on this bus**. The model hallucinates a device id
— a false claim about the machine, which is exactly the failure mode the garbage bucket
exists to price.

The coherent answers in the neural run are not the model's: system and role queries are
handled before the neural backend, so the 15 correct and 6 honest come largely from the rule
path still underneath.

## Design decisions worth recording

**Honest-roadmap counts as success.** The rubric's most consequential choice. AUTON openly
cannot do most of what a mature OS does; a system that says "I can't run a database yet, I'd
need persistent storage and a query engine" is behaving correctly. Scoring that as failure
would reward bluffing, and a model that learns to bluff about its own capabilities is worse
than one that admits them. The bar is two-sided (≥70% passing **and** <10% garbage) so a
model cannot reach 70% while hallucinating on a fifth of the prompts.

**Grading is hybrid, not fake-automatic.** 17 prompts have deterministic answers and grade on
a substring; the other 33 are free-form and go to a human. Verdicts are cached by
(fingerprint, prompt id, answer hash), so an unchanged model re-scores without asking and a
changed answer correctly re-queues.

**A substring match does not always mean CORRECT.** Four prompts (`app-02`, `app-04`,
`app-06`, `hw-05`) are answered correctly *by declining*; their match maps to
honest-roadmap. Scoring them CORRECT inflated the headline and blurred the distinction the
rubric exists to draw.

**Both backends are evaluated at `-m 256M`.** The neural backend needs ≥128M to be selected,
so the rule ISO was previously booted at 128M and the neural at 256M — and "how much memory"
then differs for reasons that have nothing to do with the model. Found when `sys-01` expected
`127 MB` and got `255 MB`. One variable changes between baselines: the backend.

## Reproducing

```bash
scripts/eval.sh --model rule                      # 66% / 34%
scripts/eval.sh --model SLM/work/auton-slm.bin    # 42% / 58%
scripts/e2e.sh --rung 3a --eval                   # eval as stage 8/8
```

Re-running either reproduces its score exactly from the verdict cache
(`tests/eval/verdicts.json`); three consecutive rule-engine runs gave byte-identical answers
and identical counts.

## Limitations

**The human grader is a single grader in a single sitting.** The plan's Task 1 validation —
"hand-grade 10 prompts twice, days apart; disagreement on ≤1" — is **not met**, and cannot
be met by the same agent in one session: a second pass minutes later is not independent. The
rubric was written first and applied top-down with boundary cases decided in advance to
limit drift, and the boundary table exists so a later grader can check consistency against
recorded decisions. Treat inter-rater agreement as unverified until a second person grades.

**Judgement calls that would move the number.** Several rule-engine answers are genuinely
borderline — `which driver should I use for my nic` returns a device list that *contains*
`8086:100e(e1000)`. I graded it garbage (non-responsive, answers a different question);
grading it correct is defensible and would lift the rule baseline a few points. The
consistent rule applied: a clarification request is garbage when the machine could have
answered, honest-roadmap when it genuinely could not.

**The eval set must stay disjoint from 3b's corpus.** These 50 prompts are now fixed. Phase
3b's Task 2 has to assert disjointness from its side; that guard is the single most important
one in 3b, because contamination makes every later quality claim silently false.

## Acceptance

- [x] 50 prompts covering six intent classes plus out-of-domain
- [x] Runner scores automatically where deterministic, queues the rest, caches verdicts
- [x] Rule-engine and rung-3a baselines recorded with their manifests
- [x] Unchanged model reproduces its score — exactly, not merely within noise
- [x] Eval reported as an `e2e.sh` stage (`--eval`, stage 8/8)
- [ ] **Rubric written; two gradings agree on ≥9/10 — partially met.** Rubric written with
      boundary cases pre-decided; the two-pass agreement check is not satisfiable by one
      grader in one session. See Limitations.
