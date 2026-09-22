# Conformance corpora

Does this chip honour its own documentation? Each entry here is one check, and every entry
carries the four fields that make an answer meaningful:

| Field | Meaning |
|---|---|
| `id` | stable name, used in verdicts and in any disclosure |
| `clause` | **the citation**: SDM section, or IEEE 754-2019 clause. An entry without one is not a conformance check, it is an opinion |
| `class` | `semantic` (a computed result) or `fault` (an architected exception) |
| `guarantee` | `architectural` (the manual promises it for every implementation) or `model-specific` (true of some parts). **Only `architectural` entries can fail a chip**; a model-specific divergence is reported as *not assertable* |
| `oracle` | where the expected answer comes from: `softfloat` for semantic entries, `architecture` for faults |

## The oracle rule

A semantic entry's expected result is computed by **Berkeley SoftFloat**, on the host, in
integer arithmetic. It is never computed by the hardware under test, and never by a model. A
suite whose oracle is the thing under test detects only self-inconsistency — which is the whole
reason this directory exists (`auton-hardware-truth.prd.md`, Open Question 4).

`scripts/fetch-softfloat.sh` pins the oracle by commit and checks its SHA-256. An oracle nobody
can reproduce is not evidence.

## What a zero means

A clean run prints `0 divergences across N clause-cited checks on <silicon identity>`. **Zero is
a finding and is published as one.** Modern parts are expected to pass: the value is in the
method and the citation trail, not in finding a bug. A suite that only reports when it finds
something teaches nobody what was checked.

## What this cannot say

Under emulation the results are QEMU's, not silicon's (`agent/hardware/CONFORMANCE-HARDWARE.md`).
A run records the identity it ran on, and a verdict from an emulated CPU says something about
the emulator. Real-silicon runs are `w15-intent-real-silicon` and the metal plan.
