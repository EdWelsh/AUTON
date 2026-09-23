# Plan: Intent-Scoped SLM Corpus (intent-D)

**Source PRD**: `.claude/PRPs/prds/auton-intent-to-os-compiler.prd.md` — phase D
**Complexity**: Small — and the cheapest falsification of the most consequential hypothesis
in the PRD set

## Summary

`build_corpus.py` generates one 555-record corpus covering all seven intent classes,
regardless of what the target OS is for. The PRD's central claim is that the model is bad
because it is **general**: most measured garbage was cross-intent mis-routing, and intent
classes that cannot coexist in an image cannot mis-route into each other.

This plan adds `--manifest`, folds in the grounding fix, and **re-measures**. Either the
garbage rate falls without any modelling change — removing a large amount of later work — or
it does not, and the 22% is a capacity ceiling that changes the whole plan. Both answers are
worth more than anything else in Wave 1.

## Evidence

- `SLM/tools/build_corpus.py:180` `build()` takes only a seed. No intent parameter exists.
- 555 records across `HARDWARE_IDENTIFY, DRIVER_SELECT, INSTALL_CONFIGURE, APP_INSTALL,
  SYSTEM_MANAGE, TROUBLESHOOT, OUT_OF_DOMAIN`.
- Rung 3b: **78% correct-or-honest / 22% garbage**. 6M → 48M gave 74%/26%, so capacity is not
  the constraint (`e2e-rung3b-training-attempts.md`).
- The observed garbage is cross-intent: `i need gpu access` → the NIC, `can i run nginx` → the
  kubernetes roadmap, `check everything` → the DHCP lease. All three answers belong to intent
  classes a Doom image would not contain.
- `build_corpus.py:37` `UNKNOWN_DEVICES` includes `10ec:8139` and `1022:2000` — **ids absent
  from this bus** — with 14 records each. The model learned a deflection template with a
  real-looking id baked in and emits it for questions containing no device: 5 phantom
  citations per 50 novel turns, 0 from the deterministic path.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Generator shape | `build_corpus.py:180-260` | `add(text, response, intent, fact)` with an eval-collision filter already wired in |
| Contamination guard | `build_corpus.py:_eval_prompt_index` | Exclusion at generation time, verified by a test — never hoped for |
| Disjointness test | `SLM/tests/test_corpus_disjoint.py` | Exact + ≥0.9 Jaccard against all eval prompts; conflicting-answer detection |
| Grounding check | `scripts/lib/session_probe.py:phantom_devices` | An answer must not name a PCI id absent from the bus — already an automated session property |
| Measurement | `scripts/eval.sh` | 65 graded prompts, cached verdicts, two-sided bar |

## Files to Change

| File | Action | Why |
|---|---|---|
| `SLM/tools/build_corpus.py` | UPDATE | `--manifest`; scope classes; fix `UNKNOWN_DEVICES` |
| `SLM/tests/test_corpus_disjoint.py` | UPDATE | Assert scoping actually excludes, and that no off-bus id is taught |
| `.claude/PRPs/reports/e2e-intent-scoped-corpus.md` | CREATE | The measurement, including a negative result |

## Tasks

### Task 1: Fix the phantom-id root cause first
- **Action**: `UNKNOWN_DEVICES` draws **only** from ids present on the target bus. Add records
  teaching that a question with **no** device id gets a clarification, not an
  unknown-device answer — that is the actual gap, since the model emits the template for
  `check for exposed APIs`.
- **Why first**: it is independent of scoping and it is a truthfulness defect. It also makes
  the scoping measurement cleaner, since phantom citations currently pollute the garbage count.
- **Validate**: a test asserts no corpus response contains a PCI id absent from the bus
  manifest; session `grounding` moves from FAIL to PASS.

### Task 2: `--manifest` scoping
- **Action**: Accept a capability manifest (intent-A/B's output, or a hand-written stub until
  those land) and generate only the classes the image serves, inheriting `excludes`. An image
  with no network ships no DHCP-lease records.
- **Mirror**: keep the eval-collision filter unconditional — scoping must not become a way to
  smuggle eval prompts back in.
- **Gotcha**: the corpus must still contain enough tokens for `train.py`'s
  `seq_len × batch_size` floor. Rung 3a hit exactly this: 61 tokens rejected at the stock
  64×32. A tightly scoped corpus may need a smaller batch, or padding with in-scope
  paraphrases.
- **Validate**: two manifests produce measurably different corpora; neither contains an
  excluded class.

### Task 3: Retrain and re-measure honestly
- **Action**: Train on a scoped corpus, export, boot, and score against the **65**-prompt eval
  — grown from real sessions, not the original 50. Record every attempt including failures, as
  rung 3b did.
- **Constraint**: the eval set spans all classes, so a scoped model will legitimately decline
  out-of-scope prompts. **Score in-scope and out-of-scope separately** — an image that
  correctly declines a kubernetes question is not wrong, and a single blended number would
  hide the actual result.
- **Validate**: in-scope garbage rate reported against 22%; the hypothesis is confirmed or
  refuted in writing.

### Task 4: Record the outcome either way
- **Action**: Write the report. If scoping fixed it, say by how much and stop. If it did not,
  say so plainly — that makes 22% a 6M capacity ceiling and redirects the PRD.
- **Mirror**: `e2e-rung3b-training-attempts.md`'s attempts table, failures included.
- **Validate**: a reader can tell which hypothesis survived.

## Validation

```bash
python SLM/tools/build_corpus.py --manifest tests/manifests/doom.json --output SLM/datasets/doom.jsonl
python -m pytest SLM/tests/test_corpus_disjoint.py -q
python SLM/tools/tokenizer.py --input SLM/datasets/doom.jsonl --output SLM/work/vocab.json --tokenize-to SLM/work/tokens.jsonl
python SLM/scripts/train.py --config SLM/configs/chat_tiny.yaml --dataset SLM/work/tokens.jsonl --output SLM/work --max-steps 3000 --seq-len 64 --batch-size 8
scripts/eval.sh --model SLM/work/auton-slm.bin       # in-scope vs out-of-scope, separately
scripts/session.sh --model SLM/work/auton-slm.bin    # grounding must be PASS
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Scoping does not improve the garbage rate | **M** | That is the finding, and it is worth having. It reframes the problem as capacity and makes the rule engine primary for longer |
| A scoped corpus is too small to train | **M** | Measured precedent: rung 3a's 61 tokens were rejected outright. Reduce batch size, or pad with in-scope paraphrases — never with out-of-scope classes |
| Blended scoring hides the result | **H** if unguarded | Task 3 splits in-scope from out-of-scope. A scoped model *should* decline out-of-scope prompts, and that must count as correct |
| The grounding fix changes the baseline mid-measurement | **M** | Task 1 lands and is measured first, so the scoping delta is attributable |

## Acceptance
- [ ] No corpus response teaches a PCI id absent from the bus; session `grounding` PASSES
- [ ] A question with no device id is taught to get a clarification
- [ ] `--manifest` produces measurably different corpora for two manifests, with `excludes` honoured
- [ ] In-scope and out-of-scope eval results reported separately against the 65-prompt set
- [ ] The hypothesis is confirmed or refuted in writing, with every attempt recorded
