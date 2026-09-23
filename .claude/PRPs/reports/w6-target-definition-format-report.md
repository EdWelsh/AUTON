# Implementation Report: Target Definition Format (D1)

## Summary

A target definition says what an image will run on. Before this, the answer was a hardcoded
literal: `BUS_DEVICES` in `SLM/tools/build_corpus.py` is QEMU's default PC, and every corpus
answer and eval expectation was written against that one machine. Nothing in the tree could say
"this image is for a different machine", so nothing could notice when it wasn't.

Three files: a format doc, two structurally different examples, and a validator that refuses.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Format doc with every field justified | Complete | `source` mandatory per fact, 4-value enum |
| 2 | Two structurally different examples | Complete | microVM written second, no field added |
| 3 | Parse and validate | Complete | three-valued identification |
| 4 | Say what is missing | Complete | every missing fact named in one run |

## The two decisions that carried weight

**`source` is mandatory per fact, not per definition.** A decision made on an assumption must be
reversible when the truth arrives, and that is impossible if the record cannot say which facts
were assumed. `firecracker.md` has probed devices and assumed silicon in the same file — a
per-definition source could not express it. This is `ident_source_t` from `arch/hal.md`
generalised from one machine to any target.

**`source: probed` outranks the registry.** The plan said a device absent from `pci.ids` is
refused. Applied bluntly that refuses `1234:1111` — QEMU's Bochs VGA, vendor id `1234` being one
QEMU invented, genuinely present on the machine and genuinely absent from the registry. The line
that works instead: absence refuses a device that only a person or an inference claims, and
passes one the machine itself reported. A device in neither the registry nor a probe is backed
by nothing, which is the phantom-id defect with a driver attached.

## Three states, not two

| State | Meaning | Exit |
|---|---|---|
| identified | in `pci.ids` | 0 |
| unknown + probed | the machine reported it; the registry does not list it | 0, reported |
| unknown + stated | nothing corroborates it | 1, refused by name |
| unavailable | no registry cached — nothing was checked | 2, `UNVERIFIED` |

The last row is the one that would have been easy to get wrong. A missing registry makes
identification *unavailable*, not unknown devices *valid* — the same distinction
`run_leakage_test.sh` draws between "not generated" and "clean". The CLI exits 3 and prints
`UNVERIFIED`, because exit status is what a build script reads.

## Validation

```
$ python agent/tools/target_spec.py --validate agent/kernel_spec/targets/qemu-pc.md
OK qemu-pc.md: vm/x86_64, 4 device(s), firmware bios
   probed but not in pci.ids: 1234:1111 (present on the machine, absent from the registry)

$ python agent/tools/target_spec.py --validate <target naming ffff:ffff as user-stated>
INVALID: phantom.md: device(s) in no registry and never probed: ffff:ffff (network, source
user-stated) — not listed in pci.ids 2026.09.15. Name a real device, or probe the machine and
record source: probed

$ python agent/tools/target_spec.py --validate <bare-metal, no devices, assumed silicon>
INVALID: thin.md: underspecified, missing: devices (class 'bare-metal' implies none; every
device must be listed); silicon (assumed on bare metal, where CPUID can be read); firmware
(something must bring real hardware up). Not defaulted — a target nobody stated is not the QEMU PC
```

21 tests pass. Mutation-tested — each of five mutations was caught:

| Mutation | Tests failed |
|---|---|
| `unverifiable` counts as ok | 2 |
| `bare-metal` implies its own devices | 3 |
| unknown device always refused, probed or not | 1 |
| missing registry treated as a pass | 2 |
| silicon `source` optional | 1 |

## Files

| File | Action | Lines |
|---|---|---|
| `agent/kernel_spec/targets/README.md` | CREATED | 91 |
| `agent/kernel_spec/targets/qemu-pc.md` | CREATED | 57 |
| `agent/kernel_spec/targets/firecracker.md` | CREATED | 67 |
| `agent/tools/target_spec.py` | CREATED | 360 |
| `agent/tests/unit/test_target_spec.py` | CREATED | 257 |

## Deviations

Task 3 said "a target naming `ffff:ffff` is refused". Implemented as refused *when unprobed* —
see the second decision above. `qemu-pc.md` would otherwise have been invalid on arrival, which
would have made the first real target definition in the tree unrepresentable.

## Acceptance

- [x] Every field justified; `source` mandatory per fact with a four-value enum
- [x] Two structurally different targets expressed without adding a field
- [x] A device absent from the ingested registry is refused by name (when unprobed)
- [x] A missing registry yields *unverifiable*, never *valid*
- [x] An underspecified target is refused with the missing facts named, never defaulted

## Amended by D6

Unverifiable originally exited 2, which collides with argparse's own exit 2 for a usage error. Changed to 3 in D6; the table above reflects the final behaviour. D6 also closed a hole here: `class: microvm` with an empty `devices` list validated without anything recording the machine type that supposedly implied it.
