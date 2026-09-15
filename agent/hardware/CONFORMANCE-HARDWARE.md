# Hardware the conformance work needs

Written early on purpose. H10 is several waves out, and acquiring silicon has a lead time
measured in weeks — naming it now is the entire point of starting portability before it is
needed.

## Why emulation is not enough

QEMU implements an *idealised* CPU. It will not reproduce:

- **Stepping-level divergence.** The premise of errata conformance is that two parts reporting
  the same family/model behave differently at different steppings. QEMU has one behaviour.
- **Microcode state.** `IA32_BIOS_SIGN_ID` commonly reads 0 under QEMU. A machine that has and
  has not had a microcode update applied is the distinction H8 answers *"is this machine safe?"*
  with, and emulation cannot present both.
- **Mercurial cores.** Google (HotOS 2021) and Meta (2021) both reported cores that compute
  incorrectly under specific conditions, at rates around one per thousand machines. That is a
  population property; it cannot be observed on one emulated CPU.
- **Semantic divergence of the FDIV class.** The Pentium defect was a wrong *answer*, not a
  wrong configuration. Finding that class requires executing the instruction on the silicon.

## What is needed, and what each proves

| Silicon | Proves | Obtainable |
|---|---|---|
| **Two Intel steppings of one family** — e.g. Alder Lake S at two steppings | That stepping-level applicability works at all. Doc 682436 lists 94 errata whose status varies by processor line; without two parts the matching logic is never exercised against a disagreement | **Likely** — used desktop parts are cheap and plentiful |
| **One AMD part, Zen 2 or later** | That the identity capture and errata join are not Intel-shaped. AMD folds the extended family where Intel folds the extended model; the code paths differ | **Likely** |
| **One Arm part with a published errata notice** — e.g. a Cortex-A72 board (Raspberry Pi 4) | That the `(implementer, part_num, variant, revision)` key works. Arm errata are keyed per *core revision*, and the same core ships in many vendors' SoCs — a shape neither x86 vendor has | **Yes, cheap** |
| **One Intel part with a known unpatched microcode revision** | That `microcode 0x0` versus `microcode unknown` versus a real revision are distinguishable in practice, not just in the renderer | **Uncertain** — requires controlling firmware update state |
| **A population of ≥1000 similar machines** | Mercurial-core detection at the rates the literature reports | **No.** Out of reach. This is a stated limit on what AUTON's conformance can claim, not a gap to close |

## Stated limits

The last row matters more than the others. AUTON can check *one machine against published
errata*. It cannot, at any realistic scale available here, detect the mercurial-core class that
motivated much of the hardware-truth PRD — that needs a fleet.

The honest framing for H10: **conformance verifies a machine against what vendors have already
documented, and reports divergence it cannot explain.** Finding a *new* defect before the public
requires either a fleet or a targeted semantic differential against a reference implementation,
and the second is the tractable one.

## Minimum viable set

If only one machine can be obtained: an x86-64 Linux host, any recent Intel part. It unblocks
H5's last acceptance criterion (live CPUID cross-check), exercises the errata join against a
real family/model/stepping, and runs the whole spine natively rather than cross-compiled.

That is already arranged in CI — `.github/workflows/portability.yml` runs `ubuntu-latest`,
which is x86-64. It is a shared runner with an unknown stepping and virtualised microcode
state, so it satisfies the identity cross-check and nothing beyond it.
