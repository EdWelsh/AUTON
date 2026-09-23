# Plan: Training Rung 3b — Real Chat Quality

**Source PRD**: `.claude/PRPs/prds/auton-e2e-train-boot-human-test.prd.md`
**Selected Milestone**: Phase 3b — Training rung: real chat quality
**Complexity**: Large — and the only phase in the PRD with genuinely unresolved research

## Summary

Make a human asking OS questions in their own words get coherent, correct answers: build a
real corpus, replace the word-level vocab with a real tokenizer, update the host↔kernel byte
contract and the kernel loader **in one atomic change**, and train to the eval bar. Blocked
on Phase 6 by design — without a baseline, "better" is unfalsifiable.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Format contract | `SLM/tools/auton_format.py:9-19, 48-102` | Docstring documents the byte layout as *the* host↔kernel contract; header is 10×uint32 |
| Vocab section | `auton_format.py:149-151` | `max_token_len` then per-token `<fI>` score+length — word-level today |
| Parity gate | `kernels/x86_64/tests/neural_parity.sh` | The guard that must pass before any ISO build |
| Kernel loader | `kernel/slm/neural/neural_backend.c` | Loader + tokenizer + inference consolidated in one TU |
| Intent classes | `kernel/include/slm.h:12-18` | 6 classes — the corpus must cover all six |
| Existing corpus | `SLM/datasets/os_tasks.jsonl` | 1687 bytes, JSONL — the shape to scale, not replace |
| Dataset tooling | `SLM/tools/dataset_builder.py`, `tokenizer.py` | Already exist; extend rather than write new |

## Files to Change

| File | Action | Why |
|---|---|---|
| `SLM/datasets/os_tasks.jsonl` | UPDATE/REPLACE | 1.7 KB cannot support free-form chat |
| `SLM/tools/tokenizer.py` | UPDATE | Word-level → real subword tokenizer |
| `SLM/tools/auton_format.py` | UPDATE | Vocab section changes shape; bump `VERSION` |
| `kernel/slm/neural/neural_backend.c` | UPDATE | Loader + in-kernel tokenizer must match the new contract |
| `kernels/x86_64/tests/neural_parity.sh` | UPDATE | Prompts are token ids — regenerate for the new tokenizer |
| `.claude/PRPs/reports/e2e-rung3b-*.md` | CREATE | Corpus provenance and eval deltas |

## Tasks

### Task 1: Corpus research (do this before anything else)
- **Action**: Decide the source and write down why. Candidates: synthesize from the kernel's
  own knowledge base (`slm.c`'s PCI-id KB and the six intent classes), mine man pages, or
  generate with a local LLM and hand-review. Define target size and the review process.
- **Open question from the PRD, unresolved**: there is no obvious public OS-domain corpus.
  Treat this as research with a written outcome, not a foregone conclusion.
- **Validate**: a written corpus plan naming source, size, licence, and review method — and
  covering all six `slm_intent_t` classes.

### Task 2: Build and review the corpus
- **Action**: Generate to the plan; hand-review a sample; hold out a test split that
  **shares no examples with the Phase 6 eval prompts** — otherwise the eval measures memorization.
- **Mirror**: existing JSONL shape in `os_tasks.jsonl`.
- **Validate**: size target met; held-out split disjoint from the eval set, asserted by a test.

### Task 3: Real tokenizer
- **Action**: Replace word-level with subword (BPE/SentencePiece). Vocab size must reconcile
  with `tiny_10M.yaml`'s `vocab_size: 32000`, which the 677-byte word vocab never approached.
- **Validate**: round-trip encode/decode on corpus samples; vocab size matches the config.

### Task 4: Contract update — host and kernel together
- **Action**: Update `auton_format.py`'s vocab section and bump `VERSION`; update the kernel
  loader and in-kernel tokenizer in `neural_backend.c`. **One atomic commit** — a version
  mismatch between exporter and loader is a silently-wrong model, not a build error.
- **Mirror**: `auton_format.py:88` already rejects a version mismatch — keep that behaviour
  and make sure the kernel does the equivalent.
- **Validate**: old `.bin` files are rejected with a clear error, not misparsed.

### Task 5: Train to the bar
- **Action**: Train tiny (then small if needed) until the Phase 6 eval clears ≥70%
  correct-or-honest with <10% garbage. Record every attempt's score, including failures.
- **Validate**: parity passes, ISO boots neural, eval clears the bar.

## Validation

```bash
PYTHONPATH=SLM .venv/bin/python -m pytest SLM/tests -q         # format + tokenizer tests
kernels/x86_64/tests/neural_parity.sh <model.bin> <ckpt.pt> <vocab.json>
scripts/e2e.sh --rung 3b
scripts/eval.sh                                                # Phase 6 scorer
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| No viable corpus source | **M** | Task 1 is research with a written outcome. 3a remains the shippable fallback; the rung can be abandoned without losing the harness |
| Corpus contaminates the eval set | **H** if unguarded | Disjointness asserted by a test in Task 2 — the single most important guard in this phase |
| Contract split across two commits ships a silently-wrong model | **M** | Atomic commit; version bump; kernel-side rejection of old versions |
| Tiny model can't reach the bar regardless of data | **M** | Escalate to `small_50M.yaml`; if that fails too, record honestly and keep the rule engine primary |
| Training time on CPU/MPS makes iteration impractical | **M** | Measure early; `--device mps` exists; consider the Proxmox box |
| 56 MB fp32 grows past the RAM budget with a bigger vocab | **M** | Watch the `-m 256M` boot; 3c (int8) is the pressure valve |

## Acceptance
- [ ] Written corpus plan; corpus built and reviewed; all six intent classes covered
- [ ] Held-out split proven disjoint from the eval set
- [ ] Real tokenizer round-trips; vocab size matches config
- [ ] Format + kernel loader updated atomically; old versions rejected loudly
- [ ] Parity passes; neural ISO boots
- [ ] Eval ≥70% correct-or-honest, <10% garbage
- [ ] Every training attempt recorded, including failures
