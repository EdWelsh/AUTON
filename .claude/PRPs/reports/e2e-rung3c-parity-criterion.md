# Rung 3c — Divergence Criterion for the int8 Path

**Phase**: 3c — Training rung: int8 quantization
**Written**: 2026-09-11, **before any int8 measurement was taken**
**Status**: fixed. Changing it after seeing results would invalidate the gate.

## Why this is written first

Parity today is exact token equality between the kernel and PyTorch. Quantization is lossy,
so exact equality will not survive it, and the harness will report FAIL. At that moment
there is an obvious temptation: loosen the check until the result passes. That is how a real
regression becomes a green run.

The criterion below is therefore fixed in advance, with its rationale, so the later
measurement can only pass or fail against it — not redefine it.

## What parity is actually protecting

Parity exists to catch **implementation divergence** between the kernel's forward pass and
the reference: a wrong stride, a transposed matrix, a broken RoPE. It has never been a
quality check — the rung-3a model passed parity while producing `<unk>` spam.

Quantization introduces a *second*, legitimate source of divergence: rounding. The criterion
has to separate the two, or it stops detecting the bug class it was built for.

## The criterion

**Primary — int8 kernel vs int8 reference, exact token match.**

The reference is recomputed from the *quantized* checkpoint, not the fp32 one. Both sides
then perform the same arithmetic on the same weights, so rounding is common to both and any
remaining divergence is implementation error. This keeps the gate exact, which is what makes
it able to catch a stride bug.

This is the check `neural_parity.sh` runs for an int8 model, and it must pass exactly.

**Secondary — int8 vs fp32, first-token agreement plus eval delta.**

Quantization error is measured separately, and is expected to be non-zero:

| Measure | Threshold | Rationale |
|---|---|---|
| First generated token identical, int8 vs fp32, on all parity prompts | must hold | The first token is chosen from the prompt's own logits with no accumulated drift. Disagreeing there means the error is large enough to change the argmax immediately, which will not stay cosmetic |
| Eval score, int8 vs the 3b fp32 baseline | within **5 points** of 78% correct-or-honest, and garbage no worse than **+5 points** over 22% | The plan's own bound. The eval is the only measure that reflects what a human would notice |

**Not used: per-logit numeric tolerance.** An epsilon on logits is easy to satisfy and says
nothing about behaviour — a model can stay within tolerance on every logit and still flip an
argmax that changes the answer. Token-level agreement is the behaviour we care about.

## What happens if it fails

Recorded now so the response is not invented later:

- **Primary fails** → an implementation bug in the kernel's int8 path. Fix the kernel. Do
  not relax the criterion.
- **First-token agreement fails** → quantization error is too large for this model. Report
  it; int8 does not ship as the default.
- **Eval drops more than 5 points** → int8 becomes opt-in and fp32 stays the shipping
  default, per the plan's own mitigation. A smaller module is not worth a worse OS.

## Scope note

The 3b model is 24 MB fp32, not the 56 MB the plan assumed (that figure was rung 3a, before
`vocab_size` was sized to the actual vocabulary). The int8 target is therefore ≈6 MB, not
≈14 MB. The plan's "≈14 MB" is restated here as **≈4x smaller than its fp32 source**, which
is the claim that was actually meant.
