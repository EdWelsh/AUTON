# Plan: Training Rung 3a — Prove the Pipeline

**Source PRD**: `.claude/PRPs/prds/auton-e2e-train-boot-human-test.prd.md`
**Selected Milestone**: Phase 3a — Training rung: prove pipeline
**Complexity**: Small (deliberately — this rung changes nothing, it establishes the baseline)

## Summary

Retrain the tiny model on the existing corpus, export, verify token-for-token parity against
PyTorch, and boot the neural ISO — with **no** corpus, tokenizer, or format changes. This is
the regression baseline every later rung is measured against, so its value comes entirely
from changing nothing.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Parity check | `kernels/x86_64/tests/neural_parity.sh:18-45` | clang-built host harness vs torch on the same checkpoint; token-id prompts; `PASS [p] -> tokens` |
| Train CLI | `SLM/scripts/train.py:107-113` | `--config --dataset --output --max-steps --seq-len --batch-size --device` |
| Export CLI | `SLM/scripts/export_auton.py:108-110` | `--checkpoint --vocab --output`; writes a sibling `.manifest.json` |
| Format contract | `SLM/tools/auton_format.py:48-102` | `MAGIC 0x4E4F5455`, `VERSION 1`, 10×uint32 header, `quant` field, `validate()` |
| Neural ISO | `kernels/x86_64/Makefile:57-71` | `iso-neural MODEL=...` with `-m 256M` for backend selection |
| Lazy torch import | SLM scripts | torch imported inside functions so `--help` works torch-free |

## Files to Change

| File | Action | Why |
|---|---|---|
| *(none — code unchanged by design)* | — | The rung's purpose is reproducibility, not change |
| `SLM/work/` artifacts | REGENERATE | New `final.pt`, `auton-slm.bin`, `vocab.json` (gitignored) |
| `.claude/PRPs/reports/e2e-rung3a-baseline.md` | CREATE | The recorded baseline: manifest, parity result, boot log, timings |

## Tasks

### Task 1: Reproduce the training run
- **Action**: `train.py --config SLM/configs/tiny_10M.yaml --dataset
  SLM/datasets/os_tasks.jsonl` with the same seed and step count as the June run. Record
  every parameter used — this is the reference invocation for all later rungs.
- **Mirror**: existing CLI defaults; do not add flags.
- **Validate**: training completes; a checkpoint lands in `SLM/work/`.

### Task 2: Export and validate the flat format
- **Action**: `export_auton.py --checkpoint --vocab --output`; then `auton_format.validate()`
  on the result.
- **Mirror**: `auton_format.py:156 validate()` — already the format's own gate.
- **Validate**: header magic/version correct, `quant == QUANT_FP32`, size ≈ 56 MB, manifest
  written alongside.

### Task 3: Token-for-token parity
- **Action**: `kernels/x86_64/tests/neural_parity.sh <model.bin> <final.pt> <vocab.json>`.
- **Gotcha from prior work**: stale host binaries have caused phantom failures — the harness
  rebuilds `/tmp/neural_forward_host` each run; confirm it actually recompiled.
- **Validate**: all three prompt cases `PASS`.

### Task 4: Boot the neural ISO
- **Action**: `make -C kernels/x86_64 iso-neural MODEL=SLM/work/auton-slm.bin` then
  `run-neural`, via the Phase 0 native path.
- **Validate**: serial shows `[SLM] Loaded model: auton-slm (fp32)` and
  `[SLM] Backend: neural` — not the rule-engine fallback.

### Task 5: Record the baseline
- **Action**: Write the report: exact invocations, manifest contents, parity output, boot
  markers, wall-clock per stage. This document is what rungs 3b/3c are diffed against.
- **Mirror**: `.claude/PRPs/reports/scratch-os-ondevice-chat-slm-report.md:1-20` — Summary,
  then an "Assessment vs Reality" table.
- **Validate**: a reader can reproduce the run from the report alone.

## Validation

```bash
scripts/e2e.sh --rung 3a                                     # the spine drives all of it
kernels/x86_64/tests/neural_parity.sh SLM/work/auton-slm.bin SLM/work/final.pt SLM/work/vocab.json
PYTHONPATH=SLM .venv/bin/python -c "from tools.auton_format import validate; print(validate('SLM/work/auton-slm.bin'))"
make -C kernels/x86_64 iso-neural MODEL=$PWD/SLM/work/auton-slm.bin run-neural
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Training is non-deterministic → parity differs run to run | **M** | Pin the seed; if parity is seed-sensitive, that is itself the finding and belongs in the report |
| Stale `/tmp/neural_forward_host` masks a real failure | **M** | Documented prior gotcha — assert the rebuild happened |
| torch version drift since June changes numerics | **M** | Record the torch version in the baseline; a mismatch explains later divergence |
| Temptation to "improve" the model here | **H** | Explicitly out of scope. Improvements are rung 3b, and 3b is blocked on Phase 6 for a reason |

## Acceptance
- [ ] Training reproduces from a recorded invocation
- [ ] Exported model passes `auton_format.validate()`
- [ ] Parity passes on all three prompts
- [ ] Neural ISO boots with `[SLM] Backend: neural`
- [ ] Baseline report written and reproducible
- [ ] Zero source changes
