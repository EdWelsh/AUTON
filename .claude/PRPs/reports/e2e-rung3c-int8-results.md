# Rung 3c — int8 Quantization: Results

**Phase**: 3c — Training rung: int8 quantization
**Recorded**: 2026-09-11
**Criterion**: `.claude/PRPs/reports/e2e-rung3c-parity-criterion.md`, fixed **before** measuring

## Summary

int8 ships the same model at **a quarter of the size**, with **byte-identical answers on all
50 eval prompts**. The RAM floor drops from ~48 MB to ~32 MB, and both quant modes load.

| Measure | fp32 | int8 | Delta |
|---|---|---|---|
| Module size | 23.5 MB | **5.9 MB** | 4.0× smaller |
| Minimum `-m` selecting the neural backend | 48 M | **32 M** | −16 MB |
| Eval, correct-or-honest | 76% | **76%** | **0 points** |
| Eval, garbage | 24% | **24%** | **0 points** |
| Answers differing across 50 prompts | — | **0** | — |

## Criterion outcome

The criterion was written first, precisely so this section could only report against it.

| Criterion | Threshold | Result |
|---|---|---|
| **Primary** — int8 kernel vs int8 reference, exact token match | must be exact | **PASS**, all 3 prompts |
| **Secondary** — first token identical, int8 vs fp32 | must hold | **Exceeded**: every token identical, not just the first |
| **Eval delta** vs 3b baseline | within 5 points | **0 points** |

The primary check compares the kernel against a reference computed from the *quantized*
weights, so rounding is common to both sides and anything left is implementation error —
which is the only thing parity has ever been able to detect. `neural_parity.sh` now reads the
model header and switches the reference automatically; fp32 parity is unchanged.

## Dequant strategy: inline, and why

`neural_backend.c` dequantizes **inline in `matmul`**, not on load. The decision follows from
one measured fact: **the model already runs in place from the Multiboot2 module** — the
loader takes pointers into module memory and copies nothing.

| Strategy | Module | Additional RAM | Resident total |
|---|---|---|---|
| fp32 in place (before) | 23.5 MB | 0 | 23.5 MB |
| int8, dequant on load | 5.9 MB | +23.5 MB | **29.4 MB — worse than fp32** |
| **int8, inline dequant** | 5.9 MB | 0 | **5.9 MB** |

Dequant-on-load would have made memory *worse* than not quantizing at all. The plan offered
both options; only one of them achieves the rung's stated goal.

Cost: one `int8 → float` conversion per weight in the inner loop, with the tensor scale
applied once to the accumulated dot product rather than per weight. Measurably slower — see
Limitations.

## The RAM floor was a constant, not a measurement

`slm_init` gated the neural backend on `NEURAL_MIN_RAM_MB 128u` — a flat threshold unrelated
to model size. A 6 MB int8 model was refused on a 96 MB machine for no reason the hardware
could justify, so quantizing would have bought nothing.

The gate now computes `module_size + NEURAL_HEADROOM_MB (24)` per module, so the floor tracks
what the model actually costs. Measured by bisecting `-m`:

```
int8 (5.9 MB):   32M -> neural     24M -> rule
fp32 (23.5 MB):  48M -> neural     40M -> rule
```

Both are far below the old flat 128 MB, which had prevented the neural backend from running
on any small machine regardless of the model.

## Also fixed

**The OS reported the wrong precision.** `slm_neural_model_info` returned the literal string
`"auton-slm (fp32)"` regardless of the loaded model, so an int8 boot printed
`[SLM] Loaded model: auton-slm (fp32)`. A false statement about the machine — exactly what
the chat rubric grades as garbage. It now reports the real mode.

## Correction (Phase 7, 2026-09-12)

**"Byte-identical answers" and "zero behavioural change" were too strong.** Both held across
the 50 Phase 6 eval prompts, but a 53-turn Phase 7 session found divergence outside that set:

```
"what's the kernel version?"
  fp32: …I do not know about that.
  int8: …I do not know about the weather.
```

The int8 answer is the worse one — "the weather" is a hallucinated topic for a kernel-version
question. What the tables below actually establish is *zero delta on the eval set*, which is a
statement about the eval's coverage, not about quantization. The prompt is now `ses-06` in
`tests/eval/prompts.jsonl` and appears in the fp32-vs-int8 diff.

The rest of this report stands: 4x smaller, RAM floor 48 M -> 32 M, parity exact.

## Limitations

**int8 inference is slower, and that is visible in the harness.** The first int8 eval scored
81%/19% with three *empty* answers at the tail: inline dequant is slow enough that the last
prompts fell behind the eval's send pacing. Re-run with `SEND_GAP=1.5` there were zero empty
answers and the score matched fp32 exactly. This is the same class of artifact that made the
3b 48M escalation first read 11%/89%. **Any int8 measurement must use relaxed pacing**, or it
measures the harness.

**fp32 remains the shipping default.** int8 is opt-in via `--quant int8`. The quality case for
switching is neutral (identical answers), and the speed case is negative; the reason to reach
for int8 is the RAM floor, on a machine that needs it.

**Quantization quality is flattering here.** 24 MB of weights over a 551-word domain with
44 distinct answers is heavily over-parameterised for its task, so int8's rounding has room
to be invisible. A model actually pressed against its capacity would not necessarily survive
as cleanly.

## Acceptance

- [x] Divergence criterion written before measurement
- [x] Format round-trips fp32 and int8 — 8 new tests in `SLM/tests/test_auton_format.py`
- [x] Kernel loads and runs int8; dequant strategy recorded with rationale
- [x] Module 4× smaller (23.5 → 5.9 MB); RAM floor demonstrably lower (48 → 32 MB)
- [x] Eval within 5 points of 3b — **0 points**; answers byte-identical
