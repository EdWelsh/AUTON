# Session Protocol — Phase 7

One page. Repeatable months later by someone who was not here.

## What a session is

One continuous conversation with the booted OS, long enough that **duration and state**
matter — not a list of independent questions. That is the whole difference from the Phase 6
eval, which scores 50 single-shot answers and cannot see drift, contradiction, or memory.

## Running one

```bash
scripts/session.sh --model rule                        --label rule-engine
scripts/session.sh --model SLM/work/auton-slm.bin      --label rung3b-fp32
scripts/session.sh --model SLM/work/auton-slm-int8.bin --label rung3c-int8
```

Artefacts land in `.artifacts/sessions/<label>-<ISO8601>/`:
`transcript.log` (raw serial), `turns.json` (the plan), `session.json` (answers + analysis).

**Nothing is fixed mid-session.** Observations only. A defect found at turn 5 stays broken
for the remaining 50 turns — that is how drift gets observed.

## Where the turns come from

Ranked by independence from whoever wrote this repo:

1. **Generated** (`tests/sessions/generated-turns.jsonl`) — the host Ollama model is asked to
   play four operator personas. It has never seen `SLM/datasets/os_chat.jsonl` or
   `tests/eval/prompts.jsonl`, so it is not reproducing our own phrasings back at us.
   Regenerate with the snippet in the phase report; it is deliberately high-temperature.
2. **Planted probes** at fixed positions — the only way to test consistency and state
   deliberately rather than hoping they come up.

Every generated turn is filtered against **both** the training corpus and the eval set. A turn
that duplicates either measures recall, not discovery, and is dropped.

## What is checked

| Property | How | Why the eval cannot |
|---|---|---|
| consistency | the same question at turn 0 and turn ~52 | eval asks each prompt once |
| statefulness | `set hostname sessionbox` early, read twice late | eval has no session |
| stability | answered-rate, first half vs second | eval has no duration |
| novelty | unanticipated input, and how it was met | eval prompts were written by us |

## After a session

Every observation gets **exactly one** disposition — no unclassified prose:

- **new eval prompt** → appended to `tests/eval/prompts.jsonl`, scored from the next run on.
  Check it is absent from the training corpus first (`SLM/tests/test_corpus_disjoint.py`).
- **defect** → written up with the evidence.
- **no action** → with the reason stated.

Findings table goes in `.claude/PRPs/reports/e2e-human-session-<rung>-<date>.md`.

## The honest limit

This is automated. It reproduces a session's *shape* — length, state, repetition, novel input
from a source that is not us — but not a person's surprise: noticing an answer is oddly
phrased, following a hunch, getting annoyed. Treat a green session as "no drift, no
contradiction, no collapse under novel input", never as "a human would be satisfied".
