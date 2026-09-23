# Plan: Training Rung 3c — int8 Quantization

**Source PRD**: `.claude/PRPs/prds/auton-e2e-train-boot-human-test.prd.md`
**Selected Milestone**: Phase 3c — Training rung: int8 quantization
**Complexity**: Medium

## Summary

Shrink the boot module from ~56 MB fp32 to ~14 MB int8 and lower the RAM floor, without
losing the eval score. The host quantizer already exists; the work is the format's reserved
quant path, kernel-side dequant, and redefining "parity" for a lossy transform *before*
measuring it.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Quantizer | `SLM/scripts/quantize.py:24-57` | Per-tensor symmetric: `qmax = (1<<(bits-1))-1`, codes + scale, stats with `compression_ratio` |
| Quantize CLI | `quantize.py:79-86` | `--checkpoint --bits {4,8} --output` |
| Reserved field | `SLM/tools/auton_format.py:19, 62, 136` | `quant` header field; `write_model` currently rejects non-fp32 — the exact extension point |
| SSE compile profile | `toolchain.mk:21-25` | Neural TUs compile with `CFLAGS_SSE`; the rest stays integer-only |
| Parity gate | `kernels/x86_64/tests/neural_parity.sh` | Exact token match today — must be redefined here |

## Files to Change

| File | Action | Why |
|---|---|---|
| `SLM/tools/auton_format.py` | UPDATE | `:136` rejects `quant != QUANT_FP32`; add the int8 write path (codes + per-tensor scales) |
| `SLM/scripts/export_auton.py` | UPDATE | Accept a quantized checkpoint and emit `quant=int8` |
| `kernel/slm/neural/neural_backend.c` | UPDATE | Dequant on load or on the fly in the forward pass |
| `kernels/x86_64/tests/neural_parity.sh` | UPDATE | Tolerance-based comparison for the lossy path |
| `SLM/tests/test_auton_format.py` | UPDATE | Round-trip tests for the int8 layout |

## Tasks

### Task 1: Define "parity" for a lossy transform — first
- **Action**: Exact token match will not survive quantization. Decide and write down the
  acceptable divergence **before** measuring: first-N-token match, per-logit tolerance, or
  eval-score delta. Pick one and justify it.
- **Why first**: choosing the criterion after seeing results is how a regression gets
  rationalized into a pass.
- **Validate**: written criterion, agreed, referenced by the harness.

### Task 2: Extend the flat format
- **Action**: Implement the int8 path: quantized codes plus per-tensor scales, `quant` field
  set, `VERSION` bumped if the layout shifts. Keep fp32 working — both must load.
- **Mirror**: `auton_format.py:126-151 write_model` structure; `quantize.py:35-57` already
  produces exactly the codes+scale payload shape needed.
- **Validate**: `SLM/tests/test_auton_format.py` round-trips both fp32 and int8; `validate()`
  reports the right quant mode.

### Task 3: Kernel-side dequant
- **Action**: Dequantize in `neural_backend.c` — on load (simple, costs RAM) or inline in the
  forward pass (saves RAM, costs speed). Choose deliberately and record why; the RAM floor is
  the point of this rung, which argues for inline.
- **Mirror**: existing loader that runs the model in place from the module.
- **Constraint**: neural TUs use `CFLAGS_SSE`; keep the rest of the kernel integer-only.
- **Validate**: host harness produces sane output from an int8 model.

### Task 4: Measure the three things that matter
- **Action**: Module size, minimum `-m` that still selects the neural backend, and eval score
  versus the 3b baseline.
- **Validate**: ≈14 MB; a demonstrably lower RAM floor; eval within 5 points of 3b.

## Validation

```bash
SLM/scripts/quantize.py --checkpoint SLM/work/final.pt --bits 8 --output SLM/work/final-int8.pt
PYTHONPATH=SLM .venv/bin/python -m pytest SLM/tests/test_auton_format.py -q
kernels/x86_64/tests/neural_parity.sh <int8.bin> <ckpt.pt> <vocab.json>   # tolerance mode
make -C kernels/x86_64 iso-neural MODEL=$PWD/SLM/work/auton-slm-int8.bin
scripts/eval.sh                                     # within 5 points of the 3b baseline
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Tolerance criterion chosen to fit the result | **M** | Task 1 fixes it in writing before any measurement |
| int8 costs more eval score than expected | **M** | Keep fp32 as the shipping default; int8 becomes opt-in rather than a downgrade |
| Inline dequant makes generation too slow to chat with | **M** | Measure tokens/sec; fall back to dequant-on-load and accept the RAM |
| Freestanding int8→float math hits the same libcall traps as before | **M** | Prior gotcha: gcc lowers builtins to nonexistent libcalls; `-fno-math-errno` and local `memcpy`/`memset` already in place — keep neural TUs on the SSE profile |
| Format churn breaks 3b models | **L** | Both quant modes load; version bump if layout shifts |

## Acceptance
- [ ] Divergence criterion written before measurement
- [ ] Format round-trips fp32 and int8
- [ ] Kernel loads and runs int8; dequant strategy recorded with rationale
- [ ] Module ≈14 MB; RAM floor demonstrably lower
- [ ] Eval within 5 points of 3b
