# Rung 3b — Corpus Plan (Task 1)

**Phase**: 3b — Training rung: real chat quality
**Written**: 2026-09-11
**Status**: research outcome, decided

## The finding that reframes this phase

Rung 3b was scoped as "the 1.7 KB corpus cannot support free-form chat". That is true but
secondary. The primary defect is that **the training data contains no answers at all**.

`SLM/tools/tokenizer.py:_read_texts` yields only `obj["text"]` — the question. Each record's
`next_action` field, which holds the answer, is never tokenized and never trained on. The
model is therefore fitted as a plain language model over a concatenation of twelve
*questions*.

Measured on the rung-3a vocabulary:

| Check | Result |
|---|---|
| Words appearing only in answers | 42 |
| …of those present in the trained vocab | **0** |

The model has no token for `Intel`, `82540EM`, or `e1000e`. It cannot produce them at any
temperature, with any amount of training. This is exactly what the Phase 6 eval recorded:

```
what is pci 8086:100e  ->  identify device 1af4:1000 which driver for the network card what driver do
```

That is not a hallucination in the usual sense. It is the model correctly continuing a
stream of concatenated questions, because questions are the only thing it was ever shown.

**Consequence for this phase**: scaling the corpus alone would change nothing. The record
format, the tokenizer, and the training stream all have to carry question *and* answer.
Corpus volume is necessary but not sufficient, and it is not the first problem to fix.

## Source decision

**Synthesize from the kernel's own knowledge base and response surface.**

Candidates considered:

| Source | Verdict |
|---|---|
| Public OS-domain corpus | **Rejected** — the PRD's open question stands; no suitable corpus exists. OS chat about *this* machine's live state is not a public dataset |
| Mine man pages | **Rejected** — wrong domain. Man pages describe Linux userland; AUTON answers about its own PCI bus, roles and live state. Licence also varies per page |
| Generate wholly with a local LLM | **Rejected as the primary source** — gemma4 does not know what this kernel answers, so its "answers" would be plausible fiction. Training a model to imitate them teaches confident wrongness, the exact failure the rubric prices as garbage |
| **Synthesize from kernel ground truth** | **Chosen** |

Rationale for the choice:

- **Correct by construction.** The answers are the strings the kernel actually produces —
  `roles.c`'s 18 capability entries with their notes, `slm.c`'s 4-entry PCI knowledge base,
  and the system-query handlers. There is no gap between what the model is taught and what
  is true of the machine.
- **No licence encumbrance.** Derived from this repository's own source (Apache-2.0).
- **Regenerable and deterministic.** The generator is committed; the corpus can be rebuilt
  and diffed. A hand-written corpus of this size could not be maintained.
- **Honest about limits by default.** Roadmap capabilities carry their real "needs X" note,
  so the honest-roadmap behaviour the rubric rewards is in the training signal rather than
  hoped for.

**Where a local LLM is used**: phrasing variety for *questions only*, never answers, and
every generated question is reviewed before inclusion. The answer side stays pinned to
kernel ground truth. This keeps paraphrase diversity without importing invented facts.

## Size target

| Quantity | Target | Rationale |
|---|---|---|
| Q/A pairs | 2,000–4,000 | Enough to teach phrasing→intent mapping for a 14M model over a narrow domain |
| Tokens | ~60k–120k | Versus 61 today. `train.py` needs `seq_len × batch_size` per step; this lifts the stock 64×32 off the floor |
| Distinct question phrasings per fact | 8–20 | Free-form input is the point; one phrasing per fact reproduces the rule engine's brittleness |
| Vocabulary | 1,500–4,000 subword units | Must reconcile with `tiny_10M.yaml`'s `vocab_size: 32000`, which the 47-word vocab never approached |

## Coverage requirements

All six `slm_intent_t` classes plus out-of-domain refusal:

| Class | Ground-truth source |
|---|---|
| HARDWARE_IDENTIFY | `slm.c` PCI KB (4 devices) + the QEMU bus AUTON actually boots on |
| DRIVER_SELECT | Same KB's driver column |
| INSTALL_CONFIGURE | System-query handlers: ip, hostname, gateway, dns, dhcp state |
| APP_INSTALL | `roles.c` — 18 entries, working and roadmap |
| SYSTEM_MANAGE | memory, uptime, status, device count |
| TROUBLESHOOT | Diagnostic phrasing over the same state, including false premises |
| OUT_OF_DOMAIN | Refusals — weather, world knowledge, arithmetic, nonsense |

Out-of-domain is a first-class class, not an afterthought: a model that cannot decline is
the one that hallucinates, and the rubric prices that at 58% garbage today.

## Contamination guard — the phase's most important control

The 50 Phase 6 eval prompts (`tests/eval/prompts.jsonl`) are **fixed and were written first**,
deliberately, before this corpus existed. The corpus must be provably disjoint from them.

Enforced by an automated test, not by care:

1. **Exact match** on normalized text (lowercase, collapsed whitespace, stripped
   punctuation) — zero overlap permitted.
2. **Near-duplicate** check — token-set Jaccard similarity ≥0.9 against any eval prompt is
   rejected, catching trivial reorderings.
3. The test runs in the normal suite, so contamination fails CI rather than being discovered
   after a quality claim has been made.

If this guard is absent or weak, the eval measures memorization and every quality number
after it is silently false. That is the reason this is a test and not a review step.

## Review method

- **Automated invariants** (every build): every record has a non-empty question and answer;
  all seven classes present; no eval-prompt overlap; every answer string traceable to kernel
  ground truth or an approved refusal template; no duplicate question text.
- **Hand review**: a random sample of 50 records read in full, plus every distinct *answer*
  template (there are far fewer answers than questions, so the answer side is reviewable
  exhaustively).
- **Held-out split**: 10% by question, split by *fact* rather than at random, so paraphrases
  of the same fact cannot straddle the split and inflate held-out accuracy.

## Licence

Derived from this repository's own source. Apache-2.0, same as AUTON. No third-party corpus,
no scraped content, no external dataset licence to honour.

## What would make this fail

Recorded now so it is not rationalized later:

- If a 14M model cannot learn phrasing→intent mapping even with correct supervision, the
  honest outcome is to keep the rule engine primary and say so. `small_50M.yaml` is the
  escalation; beyond that, the rung is abandoned and 3a remains the shippable baseline.
- If synthesized phrasing is too templated, the model will learn the templates rather than
  the intent, scoring well on held-out paraphrases and badly on the eval. The eval is the
  check that catches this, which is why it was built first.
