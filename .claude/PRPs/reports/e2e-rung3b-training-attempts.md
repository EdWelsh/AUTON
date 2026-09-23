# Rung 3b — Training Attempts and Outcome

**Phase**: 3b — Training rung: real chat quality
**Recorded**: 2026-09-11
**Eval**: `scripts/eval.sh`, 50 prompts, rubric `tests/eval/rubric.md`
**Bar**: ≥70% correct-or-honest **and** <10% garbage

## Outcome in one line

The bar is **half met**. Correct-or-honest went from 42% to 78%, clearing the ≥70% half and
beating the rule engine for the first time. Garbage fell from 58% to 22% but did not reach
<10%, and escalating the model 8× did not help.

## Every attempt, including the failures

| # | Variant | Corpus | Correct-or-honest | Garbage | Bar |
|---|---|---|---|---|---|
| — | Rule engine (baseline) | — | 66% | 34% | FAIL |
| — | Rung-3a neural (baseline) | 12 rec | 42% | 58% | FAIL |
| 1 | 6M, `chat_tiny` | 405 rec | 70% | 30% | FAIL |
| 2 | 6M, `chat_tiny` | 495 rec | **78%** | **22%** | FAIL |
| 3 | 6M, `chat_tiny` | 555 rec | 76% | 24% | FAIL |
| 4 | **48M**, `chat_small` | 555 rec | 74% | 26% | FAIL |

Attempts 2–4 sit within ±2 points, which on a 50-prompt eval is a **single answer**. Treat
them as one result, not a trend.

## The finding that mattered most

Rung 3b was scoped as "1.7 KB is too small". The real defect was that **the training data
contained no answers at all**. `tokenizer.py:_read_texts` yielded only `obj["text"]`; each
record's answer sat in `next_action`, which nothing read. The model was fitted as a language
model over twelve concatenated *questions*.

Measured on the rung-3a vocabulary: 42 words appear only in answers, and **0** of them were
in the trained vocab. The model had no token for `Intel` and could not emit one at any
temperature. Rung 3a's 58% garbage was not a capacity problem or a data-volume problem — it
was missing supervision.

Three changes produced nearly all of the improvement:

1. **Train on answers.** Vocabulary and token stream now include both sides.
2. **Teach the boundary.** The stream is `<bos> question <sep> answer <eos>`; the separator
   is what turns a flat LM stream into supervision for answering.
3. **Prompt at the separator.** `slm.c` sends `<bos> question <sep>` instead of the bare
   question. Without this the model continued the *question* — echoing fragments and
   printing `<sep>` as visible text — even once it knew the answers.

## Why escalation did not work

The plan's mitigation for a capacity ceiling was `small_50M.yaml`. Tried, at 47.7M
parameters (8× the 6M model, 182 MB fp32):

- **74% / 26% — no better than the 6M model.** Capacity is not the bottleneck.
- Inference is slow enough under emulation that the first measurement read **11% / 89%**,
  which was a harness artifact, not quality: only the first 10 of 50 prompts got answers
  before the eval finished sending. Re-measured with `SEND_GAP=6` (≈6 min per run) it scored
  74%/26%. **The 89% figure is not a result and should not be quoted.**
- A 182 MB fp32 model in a 256 MB boot budget leaves little headroom. It boots, but this is
  the pressure 3c (int8) exists to relieve.

## What the remaining 22% garbage actually is

Not hallucination — the answers are well-formed, true sentences attached to the wrong
question:

| Prompt | Answer | Problem |
|---|---|---|
| `what is my gateway address` | `Unknown PCI device 1234:1111…` | Wrong fact retrieved |
| `did you get an address from dhcp` | `Role 'DHCP server': roadmap…` | DHCP client vs server |
| `which driver should I use for my nic` | device list | Answers a different question |
| `how much ram is free` | `Memory: 255 MB RAM.` | Total, not free |

The model behaves like nearest-neighbour retrieval over training phrasings. The eval prompts
are *deliberately disjoint* from training phrasings — the contamination guard removes any
that collide — so every eval prompt is a phrasing it has never seen. That is the eval doing
its job, and it is why adding parameters did not help: the failure is generalisation across
phrasing, not capacity.

Closing the gap plausibly needs one of: many more phrasings per fact (the corpus has 8–20);
a retrieval step rather than free generation; or accepting that a 6M model over a
50-word-per-answer domain will mis-route a fifth of unseen phrasings.

## Recommendation

**Keep the rule engine primary.** The neural backend now beats it on the eval (78% vs 66%)
and is dramatically better than rung 3a, but a fifth of its answers are confidently wrong,
and the rubric's two-sided bar exists precisely to stop that shipping as a pass.

The 24 MB, 6M-parameter model is the deliverable: parity-clean, boots as the neural backend,
and is the best-scoring variant. 3c (int8) should proceed against it — the model is now
small enough that quantisation is about speed and headroom rather than survival.

## Deviations from the plan

**Subword tokenizer not adopted (Task 3).** Measured first: the domain is 394 distinct words
against a configured `vocab_size` of 32000 — 1.2% used — and word-level with complete
coverage gives **0 `<unk>` on in-domain text**. BPE would require a merge table in the
kernel's in-kernel tokenizer for a benefit this domain does not exhibit. Revisit if
vocabulary coverage ever binds; it does not today.

**`vocab_size` reconciled by new configs, not by editing `tiny_10M.yaml`.** That file is what
the rung-3a baseline reproduces against; changing it would invalidate the recorded parity
tokens and model hash.

## Bugs found and fixed along the way

- **Silent vocabulary aliasing.** `train.py` folded ids with `t % vocab_size`. When the
  vocabulary outgrew a 512 cap, 11 real words were mapped onto special tokens — `'miles'`
  became `<pad>`. A wrong model, not a smaller one. It now refuses instead of folding.
- **`out_ids[16]` with a 40-token cap.** Raising the output cap without the buffer would have
  overflowed the stack. Caught before it shipped.
- **Parity stop-condition drift.** The kernel learned to stop at `<sep>`; the torch reference
  did not, so parity reported a divergence that was only a difference in stop rules. Both
  sides now implement the same rule, and the prompts were regenerated for the v2 vocabulary.
- **Conflicting supervision.** The corpus guard caught the same question carrying two
  different answers after a corpus edit.

## Acceptance

- [x] Written corpus plan; corpus built and reviewed; all six intent classes plus OOD
- [x] Held-out split proven disjoint from the eval set — guard caught real contamination on
      its first run (`what devices`, `status`, `uptime`, `zxqw flibberty gronk`)
- [x] Format + kernel loader updated atomically; v1 models rejected by version
- [x] Parity passes; neural ISO boots with `[SLM] Backend: neural`
- [x] Every training attempt recorded, including failures
- [ ] **Real tokenizer round-trips; vocab size matches config — deviated.** Word-level
      retained on measured grounds; `vocab_size` reconciled via new configs. See Deviations.
- [ ] **Eval ≥70% correct-or-honest, <10% garbage — half met.** 78% / 22%. The garbage half
      is not met and capacity escalation did not close it.
