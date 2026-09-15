---
mitigation: fdiv-reference-check
addresses: [intel-pentium-fdiv]
class: semantic
requires: [slm]
cost: a detection pass at boot; no mitigation is possible, so no runtime cost is incurred
verify: divide a known-bad operand pair and compare against the correct quotient
        computed without the FPU; report the divergence rather than repairing it
status: unmitigatable
---

# FDIV — Incorrect Floating-Point Division

## The defect

Certain Intel Pentium processors return incorrect results from `FDIV` for particular operand
pairs. Five entries were missing from the lookup table used by the SRT division algorithm, and
for operands reaching those entries the quotient is wrong in roughly the fourth significant
decimal digit.

The machine does not hang. It does not fault. It returns an answer, and the answer is wrong.

## Why this entry exists even though nothing can be done

This is a **semantic-class** defect, and it is in the registry precisely because it has **no
software mitigation**. The processor computes a wrong answer in hardware. Nothing the OS does
changes that.

A registry that only recorded fixable defects would have no way to express the most important
thing it can say: *this machine computes incorrectly, we detected it, and we cannot fix it.*

It is also the reason `class` exists. F00F can be provoked and its fix proven. FDIV can only be
found by **comparing the machine against a reference** — which is a fundamentally different
kind of check, and the one that generalises to defects nobody has documented yet.

## Detection

1. Compute `4195835.0 / 3145727.0` on the FPU.
2. Compute the same quotient without the FPU — integer long division at sufficient precision.
3. A correct processor returns `1.333820449136241`. An affected one returns `1.333739068902037`.
4. Divergence beyond the representable error is a positive detection.

The operand pair is the one Thomas Nicely used, and it is in the public record. Other pairs
reach the same missing table entries; one is enough to detect.

## What the OS does with a positive result

- Report it, in every `is this machine safe` answer, as **unmitigatable**.
- State what is affected: any floating-point division, so any computation resting on one.
- Decline to claim a fix. Recompiling in software floating-point would avoid the FPU, but that
  is a change to every program, not a mitigation the OS can apply.

## Requirements

`slm` only — to report. There is nothing to install.

## Cost

A detection pass at boot: two divisions and a comparison. No ongoing cost, because there is no
ongoing mitigation.

## Acceptance Criteria

1. The check runs at boot and completes in bounded time.
2. On unaffected silicon it reports no divergence; on affected silicon it reports divergence
   with both values.
3. The erratum is reported as `unmitigatable` and never as `mitigated`.
4. The report names what is affected — floating-point division — rather than only the erratum id.
