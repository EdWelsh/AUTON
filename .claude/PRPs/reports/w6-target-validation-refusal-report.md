# Implementation Report: Validation and Refusal (D6)

## Summary

D1 built the format; D6 is its refusals, and it found a hole D1 had left. A `class: microvm`
target with an empty `devices` list validated on the grounds that "the machine type implies
them" — while nothing in the file recorded the machine type. The list was not implied, it was
blank, and it passed.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | What makes a target buildable, per class | Complete | one rule, not five |
| 2 | Refuse, naming what is missing | Complete | plus how to supply it |
| 3 | Three states, not two | Complete | exit 3, not 2 — see below |
| 4 | A target must not silently become another | Complete | regression test, mutation-checked |

## Task 1: one rule rather than a table of minimums

The plan asked for a minimum per class. Writing them out, they turned out to be one rule:

> Something must pin the device set — an enumeration, or a platform that fixes one.

`bare-metal` and `vm` enumerate, because nothing is implied there. `microvm`, `k8s-pod` and
`auton-hosted` may leave `devices` empty, but only once the platform is named
(`platform.hypervisor` + `platform.machine`, `platform.runtime`, `platform.host_image`). A driver
decision needs a device set; these are the only two ways to have one.

This is why `firecracker.md` gained a `platform` block. D1 forbade adding a field to make the
microVM expressible, and that constraint held — the field is added here because a *refusal*
needs it, not because a machine did.

## Task 3: exit 3, not 2

The plan said exit 3 and did not say why. Implementing it found the reason: `argparse` already
exits 2 on a usage error. D1 had used 2 for unverifiable, so a mistyped flag and a target nobody
could check returned the same status to any script reading `$?`. That is the same collapse the
phase exists to prevent, one level down.

| Code | Outcome |
|---|---|
| 0 | valid |
| 1 | refused |
| 3 | unverifiable — **not** a pass |

## Task 4: the regression test

`SLM/tools/build_corpus.py` hardcodes QEMU's PC as `BUS_DEVICES`, and that literal is why every
image so far was built for one machine without anyone deciding to. The test scans
`target_spec.py` for any `vvvv:dddd` literal and fails if one appears — a default device table
cannot be added back without the suite going red. Verified by adding one:

```
DEFAULT_DEVICES = ["8086:1237", "8086:7000"]
→ FAILED test_no_code_path_substitutes_a_default_device_set
```

## Validation

```
$ target_spec.py --validate <bare-metal, no devices>
INVALID: thin.md: underspecified, missing: devices (class 'bare-metal' implies none; every
device must be listed); silicon (assumed on bare metal, where CPUID can be read); firmware
(something must bring real hardware up). To supply these, probe the machine, state the fact, or
derive it — and record which. Not defaulted — a target nobody stated is not the QEMU PC
exit=1

$ target_spec.py --validate <microvm, hypervisor but no machine type>
INVALID: mv-nomachine.md: underspecified, missing: platform.machine (class 'microvm' takes its
device set from the platform, so the platform must be named). ...
exit=1

$ mv .cache/vendor .cache/vendor.hold && target_spec.py --validate qemu-pc.md
   unverifiable: 8086:1237, 8086:7000, 1234:1111, 8086:100e — no registry cached, so nothing
   confirms or denies these ids
UNVERIFIED qemu-pc.md: vm/x86_64, 4 device(s), firmware bios
exit=3
```

28 tests pass. The cache was moved and restored, not deleted.

## Files

| File | Action |
|---|---|
| `agent/tools/target_spec.py` | UPDATED — `platform`, `HOW_TO_SUPPLY`, exit codes |
| `agent/kernel_spec/targets/firecracker.md` | UPDATED — `platform` block + why |
| `agent/kernel_spec/targets/README.md` | UPDATED — rule 4 rewritten, exit codes |
| `agent/tests/unit/test_target_spec.py` | UPDATED — 21 → 28 tests |

## Deviations

Task 1 states one rule instead of a per-class table; the per-class minimums fall out of it. D1's
report claimed exit 2 for unverifiable — corrected to 3 here, with the collision as the reason.

## Acceptance

- [x] Minimum viable target stated per class, each with its reason
- [x] An underspecified target is refused naming the missing facts and how to supply them
- [x] Three states — valid, unverifiable, refused — with distinct exit codes
- [x] A regression test proves no path substitutes a default device set
