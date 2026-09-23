# Rung 3d — Inference Hardening: Results

**Phase**: 3d — Inference hardening
**Recorded**: 2026-09-11

## Summary

Every way the neural backend can fail now produces a **named reason** on the console and a
usable `auton>` prompt on the rule engine. Degenerate generation falls back instead of being
printed. The E2E spine asserts the fallback matrix on every run, so honest degradation is a
tested property rather than a hoped-for one.

## Fallback matrix (Task 1)

All eight cases boot to a working prompt. Before this rung, the four corrupt-module cases
were **indistinguishable** — each printed only `Backend: rule-engine`, which is exactly what
a machine with no model prints.

| Scenario | Console | Backend | Boots |
|---|---|---|---|
| Good fp32 model | `Loaded model: auton-slm (fp32)` | neural | yes |
| Good int8 model | `Loaded model: auton-slm (int8)` | neural | yes |
| Truncated module | `Model rejected: module truncated` | rule | yes |
| Bad magic | `Model rejected: not an AUTON model (bad magic)` | rule | yes |
| Bad version | `Model rejected: unsupported format version` | rule | yes |
| 200-byte module | `Model rejected: module truncated` | rule | yes |
| Module too big for RAM | `Model rejected: needs 47 MB, have 39 MB` | rule | yes |
| No module at all | `No model module; rule engine only` | rule | yes |

`slm_neural_load_model` now returns distinct codes (`SLM_ERR_MAGIC`, `_VERSION`, `_QUANT`,
`_GEOMETRY`, `_TRUNCATED`, `_NOMEM`, `_ARGS`) and `slm_neural_error_text` renders them.

**A real bounds bug was fixed.** The loader validated the header, then walked the weight
pointers and parsed the tokenizer block without ever checking the weight section fit inside
the module. A truncated module therefore parsed its tokenizer from whatever happened to
follow in memory. The module is untrusted input — it is whatever GRUB was handed — so the
loader now computes the expected weight size for the declared quant mode and rejects short
modules before any pointer walks off the end.

At `-m 32M` the message is `No model module`, not a size rejection: GRUB cannot load a
23.5 MB module into 31 MB, so from the kernel's side there genuinely is no module. The
message is accurate.

## Load time and RAM floor (Task 2)

Boot → `[SLM] Ready`, QEMU on an M-series host:

| Model | Module | Load to Ready | Min `-m` selecting neural |
|---|---|---|---|
| fp32 | 23.5 MB | 3 s | 48 M |
| int8 | 5.9 MB | 2 s | 32 M |

**The 128 MB threshold was corrected, not confirmed.** It was a flat constant
(`NEURAL_MIN_RAM_MB 128u`) unrelated to model size — a 6 MB model was refused on a 96 MB
machine. Rung 3c replaced it with `module_size + 24 MB headroom`; the floors above are the
measured result of bisecting `-m`.

## Degenerate-output guard (Task 3)

`slm_neural_is_degenerate` rejects output that is tokens but not an answer: an empty
generation, four identical tokens in a row, or a period-2/3 cycle repeating at the tail.
On detection `slm_neural_infer` returns 0, which the existing caller already treats as
"fall back to the rule engine". Allocation-free and freestanding, as required.

Tested from both directions, because a guard that only runs when a model misbehaves is a
guard nobody has checked:

- **`tests/degenerate_test.c`** — 11 cases, run by `tests/run_degenerate_test.sh`. Five
  degenerate shapes caught; six legitimate shapes (normal sentence, three-in-a-row, a word
  repeated non-adjacently, 1- and 2-token outputs, a pair repeated twice) correctly passed.
- **No false positives in the live system**: the eval score and all 50 answers are
  byte-identical with the guard in place (76% / 24%, unchanged).
- **Wiring proven**: lowering the run threshold from 4 to 2 changes exactly one answer,
  confirming the guard is reached and acted on. Restored to 4.

**An honest limitation.** An under-trained model was built specifically to trigger the
run/cycle detection and did *not*: with loss ~240 it emits `<eos>` immediately, so the
pre-existing empty-output path caught it first. The run and cycle branches are therefore
verified by unit test and by the threshold experiment, **not** by a live model that exhibits
them. The behaviour they target was observed earlier in rung 3b (`driver: driver: driver:`),
which is why the guard exists, but that model no longer exists to re-demonstrate it.

## Spine coverage (Task 4)

`scripts/e2e.sh` gains stage `[7/8] fallback`, which boots a truncated model and a
no-module ISO and asserts the `fallback-rejected` and `fallback-no-module` marker sets from
`acceptance_tests.py`. Three new `AcceptanceTest` entries cover the same markers so the
Python gate and the shell harness stay single-sourced.

```
[7/8] fallback   ... ok (4s)
    --- corrupt module ---   PASS Model rejected: / Backend: rule-engine / BOOT OK
    --- no module ---        PASS No model module / Backend: rule-engine / BOOT OK
```

Full run: GREEN 8/8 in 26 s.

## Verification

| Check | Result |
|---|---|
| agent unit tests | 800 passed |
| SLM tests | 93 passed |
| Degenerate guard test | 11/11 |
| `run-acceptance.sh` | exit 0 |
| Parity, fp32 and int8 | ALL PASS |
| Eval, unchanged by hardening | 76% / 24% |

## Acceptance

- [x] Every enumerated failure mode has a stated fallback and a distinct marker
- [x] Load time and true RAM floor measured and recorded (threshold corrected, not confirmed)
- [x] Degenerate-output guard triggers on bad output, never on the baseline — with the
      live-trigger limitation recorded above
- [x] Fallback matrix asserted by the E2E spine
- [x] No garbage answer reachable by any tested path — every tested failure reaches the rule
      engine, which cannot emit degenerate output

## Not done

The plan's risk table suggests reporting the **fallback rate** in the eval, so a rising rate
is visible as a signal rather than passing as a success. The eval records which backend
answered only implicitly (via the model fingerprint), not per-prompt. Worth adding when the
neural path is the default; today fp32 neural answers every prompt it is asked.
