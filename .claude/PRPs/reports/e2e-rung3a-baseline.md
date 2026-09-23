# Baseline: Training Rung 3a — Prove the Pipeline

**Phase**: 3a — Training rung: prove pipeline
**Recorded**: 2026-09-11
**Base commit**: `bbc9fea` (Phase 2 spine merged to main)

This is the reference every later training rung is diffed against. Its value is that
nothing about the model changed — only that the chain is now known to be reproducible and
that its two gates were found not to be.

## Summary

The tiny model retrains on the existing corpus, exports to the flat format, passes
token-for-token parity against PyTorch, and boots as the neural backend. The run is
**bit-for-bit deterministic**: two independent runs produce byte-identical checkpoints and
byte-identical exported models.

Two defects were found in the verification chain itself, both of which could report success
while checking nothing. Fixing them is the only reason this rung touched source at all.

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Small — "changes nothing" | Small in pipeline terms; two gate defects made it not a no-op |
| Source changes | **Zero** | Two — `neural_parity.sh`, `kernels/x86_64/Makefile`. Both are gates that could pass vacuously |
| Training determinism | **M** risk — "may be seed-sensitive" | Resolved: bit-for-bit identical across runs |
| Stale host binary masks failure | **M** risk | Not reproducible — the harness does recompile. A *different* phantom was found instead |

## Reference invocation

Every command below is run from the repo root with `.venv/bin/python`.

```bash
# 1. Tokenize (47-token learned vocab from a 1.7 KB corpus)
.venv/bin/python SLM/tools/tokenizer.py \
  --input SLM/datasets/os_tasks.jsonl \
  --output SLM/work/vocab.json --tokenize-to SLM/work/tokens.jsonl

# 2. Train. seq-len/batch-size are NOT defaults: the corpus yields 61 tokens and
#    train.py requires seq_len*batch_size, so the stock 64x32 is rejected outright.
.venv/bin/python SLM/scripts/train.py \
  --config SLM/configs/tiny_10M.yaml --dataset SLM/work/tokens.jsonl \
  --output SLM/work --max-steps 200 --seq-len 16 --batch-size 2

# 3. Export to the flat format
.venv/bin/python SLM/scripts/export_auton.py \
  --checkpoint SLM/work/final.pt --vocab SLM/work/vocab.json \
  --output SLM/work/auton-slm.bin

# 4. Parity against torch
kernels/x86_64/tests/neural_parity.sh \
  SLM/work/auton-slm.bin SLM/work/final.pt SLM/work/vocab.json

# 5. Neural ISO + boot
make -C kernels/x86_64 iso-neural MODEL="$PWD/SLM/work/auton-slm.bin"

# Or all of it, with artifacts and a verdict:
scripts/e2e.sh --rung 3a
```

The seed is not a flag: `train.py` hardcodes `torch.manual_seed(0)`.

June's original step count is **not recoverable** — `SLM/work/` is gitignored and was
overwritten by Phase 2's runs. The invocation above supersedes it and is what
`scripts/e2e.sh` encodes (`MAX_STEPS=200 SEQ_LEN=16 BATCH_SIZE=2`).

## Environment

| Component | Version |
|---|---|
| Python | 3.13.13 |
| torch | 2.12.0 |
| clang (parity harness) | Apple clang 21.0.0 |
| x86_64-elf-gcc | 16.2.0 |
| QEMU | 11.1.1 |
| Host | macOS, native (no Docker) |

## Baseline artifacts

| Artifact | SHA-256 | Bytes |
|---|---|---|
| `SLM/work/final.pt` | `e554ee72444cf7ac5f36b7055e7a43b1ef88d1d190cad4fe52ce542f3ebff82c` | 56,392,127 |
| `SLM/work/auton-slm.bin` | `b74e908d9cdfe4af6a280ab0e2a257b43a87e40faff0e7c3ba3bc18d81eb66e5` | 56,630,531 |
| `SLM/work/vocab.json` | `d9d0939e42d9e38af7e16cb2aa2270c0312d525697dba3aeece6dbc2886ef398` | 677 |

**Determinism**: two independent full runs produced identical `final.pt` SHA-256, and the
exported model SHA matched a run from the previous session's Phase 2 work. Corpus → tokens →
checkpoint → flat model is reproducible end to end on this host.

## Training result

| Field | Value |
|---|---|
| steps | 200 |
| final_loss | 1.434476416761754e-06 |
| perplexity | 1.0000014344774457 |
| parameters | 14,093,568 |
| corpus | 1,687 bytes, 12 records → 61 tokens, 47-token vocab |
| wall clock | ~6 s |

The loss is effectively zero because the model memorises a 12-record corpus. That is the
expected and intended outcome for this rung: it proves the pipeline, not chat quality.
Rung 3b is where quality is trained, and it is gated behind Phase 6's grading for that reason.

## Flat-format validation

`auton_format.validate()` → `FlatHeader(dim=256, hidden_dim=1024, n_layers=6, n_heads=4,
n_kv_heads=2, vocab_size=32000, seq_len=2048, quant=0)`

| Check | Expected | Actual |
|---|---|---|
| magic | `0x4E4F5455` | `0x4E4F5455` |
| version | 1 | 1 |
| quant | `QUANT_FP32` (0) | 0 |
| size | ~56 MB | 56,630,531 |
| manifest | written alongside | `auton-slm.bin.manifest.json` |

## Parity (token-for-token vs PyTorch)

```
PASS [2 4 5]   -> 17 18 19 20 21 22 8 9 6 7 10 4
PASS [2 29 30] -> 31 32 12 33 13 13 13 13 13 13 13 13
PASS [2 4]     -> 5 17 18 19 20 21 22 8 9 6 7 10
NEURAL PARITY: ALL PASS
```

These exact sequences are the baseline. A later rung producing different tokens is expected
(different weights); a later rung where kernel and torch **disagree** is a regression.

## Neural boot

```
[SLM] Rule engine initialized
[SLM] Loaded model: auton-slm (fp32)
[SLM] Hardware scan complete: 4 devices
[SLM] Loaded driver: e1000
[SLM] Backend: neural
[SLM] Ready
[BOOT] OK
```

The ISO was verified to carry the model just trained by comparing the staged
`isodir-neural/boot/auton-slm.bin` SHA against `SLM/work/auton-slm.bin` — not by trusting
that `make` rebuilt it. See defect 2.

## Stage timings (via `scripts/e2e.sh --rung 3a`)

| Stage | Seconds |
|---|---|
| preflight | <1 |
| train | 6 |
| export | 1 |
| parity | 2 |
| iso | 0 |
| boot | 4 |
| markers | 1 |
| transcript | 14 |
| **total** | **28** |

## Defects found (the reason this rung was not a no-op)

### 1. `neural_parity.sh` reported ALL PASS while comparing nothing to nothing

The script `cd`s to `kernels/x86_64` before using its arguments. `$PYTHON` was absolutized
for exactly that reason (`# absolutize before cd`), but `MODEL`, `CKPT` and `VOCAB` were not.
Given **relative** paths — including the exact command in this phase's own plan and in the
Phase 2 plan's validation block — the kernel harness printed `cannot open ...`, torch raised
`FileNotFoundError`, both sides produced empty strings, and `"" = ""` reported:

```
PASS [2 4 5] -> 
PASS [2 29 30] -> 
PASS [2 4] -> 
NEURAL PARITY: ALL PASS
```

Fixed two ways: the three paths are absolutized before the `cd` and checked for existence,
and empty output from either side is now an explicit failure rather than agreement. A gate
that cannot fail is worse than no gate — every rung's parity claim rests on this.

### 2. A new model did not rebuild the neural ISO

`$(NEURAL_ISO)` depended only on `$(KERNEL)` and the GRUB config, so `make iso-neural
MODEL=<new>` reported `Nothing to be done` and left the **previous** model inside the ISO.
Demonstrated by pointing `MODEL` at different content and observing an unchanged ISO SHA.

Consequence for the roadmap: rung 3b would train a better model, boot the 3a model, and pass.

Adding `$(MODEL)` as a prerequisite was insufficient — switching to a model whose file is
*older* than the existing ISO still satisfies make, and it also broke the friendly
"set MODEL=..." error by preventing the recipe from running at all. Which model is inside an
ISO is not expressible as an mtime dependency, so the target now always rebuilds via a
`FORCE` prerequisite. The build is sub-second.

Verified after the fix: switching models rebuilds; a missing `MODEL` and a nonexistent
`MODEL` both produce their original errors; the staged model SHA matches the trained model.

## Acceptance

- [x] Training reproduces from a recorded invocation — and is bit-for-bit deterministic
- [x] Exported model passes `auton_format.validate()`
- [x] Parity passes on all three prompts — genuinely, for the first time with relative paths
- [x] Neural ISO boots with `[SLM] Backend: neural`, carrying the model just trained
- [x] Baseline report written and reproducible
- [ ] **Zero source changes — deviated.** Two files changed, both verification gates that
      could pass vacuously. A baseline resting on gates that cannot fail would be worthless,
      and the plan's own risk table anticipates exactly this class ("phantom failures").
      No change to the model, corpus, tokenizer, or flat format.

## For rungs 3b / 3c

Diff against this document. Specifically:
- Parity must still be kernel == torch; the token values will differ.
- `quant` becomes `QUANT_INT8` in 3c; `validate()` must accept it and the size drops ~4x.
- Loss near zero here is memorisation of 12 records, not quality — do not treat it as a bar.
- Re-record torch's version: numeric drift there is the most likely cause of a later
  parity divergence that is not a real regression.
