# Phase 7 — Session Round 2

**Recorded**: 2026-09-12
**Protocol**: `tests/sessions/PROTOCOL.md`
**Turns**: `tests/sessions/generated-turns-batch2.jsonl` (fresh sample, five new personas)

## Why run it again

Round 1 established the harness and found one defect. A second round is only worth the time
if it does something the first could not, so it does two things: a **reproducibility check**
on round 1's exact turns, and a **discovery run** on a fresh sample.

Both paid off — and the second round found a bug in the harness itself.

## Reproducibility: the harness does not flake

Round 1's rule-engine session replayed verbatim via the new `--replay` flag:

```
turns compared:            53
differing (raw):            0
differing (uptime-normed):  0
```

Zero differences, not even in the uptime counters. Any change between rounds is the system,
not measurement noise — which is what makes the discovery half interpretable.

`--replay` exists because a fresh plan is *not* the same plan: the planner filters generated
turns against the eval set, and that set grows as findings are promoted. Round 2's planner
correctly dropped all 8 prompts promoted in round 1 — once a finding becomes an eval prompt it
stops being discovery and becomes regression coverage. Comparing rungs now requires replaying
one plan against each.

## A harness bug, found by running it again

Round 2's batch was larger, and `turns[:limit]` silently truncated the **end** of the plan —
removing `consistency-b`, `state-read-late` and `state-restore`. Those are precisely the
probes that test consistency *over distance*.

The analyser then reported **no consistency finding at all** rather than a failure, and the
session printed `ALL PASS`. A check that quietly does not run looks exactly like a check that
passed.

Fixed two ways: generated turns are budgeted so probes can never be crowded out, and
`REQUIRED_PROBES` is asserted both when planning (raises) and when analysing (a failing
`probe-coverage` finding). Round 1's 55-turn plan fit under the limit by luck, which is why
this only appeared on the second run.

## Results, all three rungs, 60 turns each

| Property | rule | 3b fp32 | 3c int8 |
|---|---|---|---|
| consistency (turn 0 vs 57) | PASS | PASS | PASS |
| statefulness (×2) | PASS | PASS | PASS |
| stability | PASS | PASS | PASS |
| follow-up (×2) | PASS | PASS | PASS |
| **grounding** | **PASS** | **FAIL** | **FAIL** |

## Findings

### F6 — The neural model cites hardware that is not there. **DEFECT (new, and the important one)**

Objective measure, added to the harness this round: an answer must not name a PCI id absent
from this machine's bus.

| rung | novel turns | deflected | answered | **cites absent hardware** |
|---|---|---|---|---|
| rule engine | 50 | 34 | 16 | **0** |
| 3b fp32 | 50 | 27 | 23 | **5** |
| 3c int8 | 50 | 27 | 23 | **5** |

```
net list all                        -> Unknown PCI device 10ec:8139…
check for exposed APIs              -> Unknown PCI device 1022:2000…
what physical ports are accessible  -> Unknown PCI device 10ec:8139…
```

None of those questions contains a device id. The answers invent one.

**Root cause is my own corpus design.** `build_corpus.py` sets
`UNKNOWN_DEVICES = [... "10ec:8139", "1022:2000"]` — two ids that are *not* on this bus — and
generates 14 records each teaching `"Unknown PCI device <id>. No matching driver…"`. The model
learned a deflection template with a real-looking id baked in, and now emits it for questions
with no device in them. A deflection that names hardware reads as a factual claim.

*Recommended fix (not applied — out of this phase's scope):* draw `UNKNOWN_DEVICES` only from
ids actually on the bus, and add records teaching that a question with **no** id gets a
clarification rather than an unknown-device answer.

*Disposition*: defect, with `ses-09`, `ses-10` promoted to the eval set, and `grounding` added
as a permanent harness property so any rung is scored on it.

### F7 — Where the rule engine deflects, the neural model answers wrongly. **DEFECT**

The neural rungs answer 23 of 50 novel turns against the rule engine's 16. Every one of the 9
turns where neural answers and rule deflects is wrong:

| typed | 3b answered |
|---|---|
| `check hw info` | *"Yes. DHCP assigned 10.0.2.15…"* |
| `i need gpu access` | *"The NIC is 8086:100e; its driver is e1000…"* |
| `can i run nginx` | *"Role 'kubernetes': roadmap…"* |
| `kubelet check` | *"Yes. DHCP assigned 10.0.2.15…"* |
| `check everything` | *"Yes. DHCP assigned 10.0.2.15…"* |

**This materially qualifies the Phase 3b conclusion.** 3b scored 78% correct-or-honest against
the rule engine's 66% and I reported it as beating the rule engine. On a broad sample of real
operator input, its extra coverage is entirely hallucination — and by the rubric's own logic a
confident wrong answer is *worse* than an honest deflection. The eval's 58 prompts are mostly
tidy in-domain natural language, so they under-sample exactly the register where the neural
model degrades.

*Disposition*: defect. `ses-11`…`ses-15` promoted so the next rung is scored on this register.

### F8 — int8/fp32 divergence is real but rare. **REFINES F1**

Round 1 found one divergence (`"what's the kernel version?"`). Across round 2's 57 turns:
**0 divergences.** The Phase 3c defect stands as recorded, but it is narrow — not a systematic
quantization problem. Reported here so F1 is not read as broader than the evidence supports.

*Disposition*: no action beyond the correction already made to the 3c report.

### F9 — Elliptical follow-ups: the rule engine is honest, the model invents. **EVAL PROMPT**

After *"what is pci 8086:100e"*, asked *"what driver does it need?"*:

```
rule:   Name the device, e.g. 'driver for 8086:100e'.
neural: Unknown PCI device 1af4:1001
```

The rule engine asks for the referent it does not have. The model names a device that is
neither the referent nor on the bus — the same mechanism as F6.

*Disposition*: `ses-14` promoted. Note the harness's own follow-up check passed here: it only
detects a follow-up that *parrots* the previous answer, which is too weak to catch a
confidently wrong new one. Recorded as a known limit of the check.

## Eval set growth

| | prompts |
|---|---|
| After Phase 6 | 50 |
| After round 1 | 58 |
| After round 2 | **65** |

## Limits, unchanged

Still no human. The generated turns are a model's idea of an operator — better than my own
guesses, since gemma4 has seen neither the corpus nor the eval set, but not a person. The new
registers this round (impatient shorthand, Linux assumptions, security probing, non-technical,
compound questions) produced `check everything` and `i need gpu access`, which I would not
have written. A person would still produce stranger input than either of us.

The recommendation from round 1 stands and is now better evidenced: **run one real human
session before putting rung 3b in front of anyone.** F7 in particular suggests the neural
model should not be the default until it learns to decline.
