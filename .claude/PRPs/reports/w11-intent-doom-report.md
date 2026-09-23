# Implementation Report: I1 Doom (intent-G)

## Summary

**Doom is not unblocked, and it now stops at a different gate.** V7 left four blockers. This
phase removed two, changed one from "needs a decision" to "decided", and found a fifth that
nobody had listed.

| Blocker (V7's list, plus one) | Before | After |
|---|---|---|
| `play-doom` service spec | missing | **written.** It validates, resolves to a closed 8-subsystem slice, and carries no stub marker |
| `input` (ps2-keyboard) | `status: undrivable`, needs a human decision | **decided: accepted on convention plus tests**, recorded; `status: specified` |
| `module-asset` | specified in name only | **specified** (`pkg.md`, *Module assets*). Deliberately **unmapped** |
| `framebuffer` | specified, not implemented | unchanged. Needs a tree |
| **doomgeneric licence** (new) | not listed | **open, and a human's call.** GPL-2.0 engine source, not inventoried; `licences.yaml` says a GPL port is `depends-on-use`, so a person must decide |

`package_image.py` now reports `[gate: sources]`: there is no generated kernel tree. Before this
phase it stopped earlier, at a stub spec. The next gate after that, `[gate: capabilities]`, will
refuse `framebuffer` and `module-asset` as unmapped, which is correct: they are specified and
not implemented.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Emit `play-doom.md` through the handoff | Complete | `intent_service.py` emitted the front-matter and the body is written. It cites `doomgeneric.h` and Multiboot2 §3.6.6/§3.6.12 and does not restate `drivers.md` |
| 2 | Take the input decision in writing | Complete | Decision (the project owner, 2026-09-21): **accept on convention plus tests.** See below |
| 3 | `module-asset`: the WAD as a boot module | Complete, with a deviation | Specified in `pkg.md`, not mapped. See *Deviations* |
| 4 | Say what is still missing | Complete | the table above |

## The input decision, and how it is recorded

`drivers/README.md` has no way to say "accepted without a specification". The only valid status
for a device with no inventoried spec was `undrivable`, and `driver_spec` refused anything else.
This is the "second record cannot be expressed without it" case the format rules require before
adding a field. So there is now one field, in one place:

- `platform-devices.yaml` → `i8042.accepted: {basis, evidence}`. `specified_by` stays `null`, so
  nothing claims a document exists.
- `driver_spec.check_devices` admits an unidentifiable platform device **only** at
  `status: specified`, and **only** when that block is present. It reports the device as
  `accepted without a specification`. It never admits `implemented`.
- `driver_strategy.py --device platform:i8042` **still refuses every strategy.** That is the
  truth: no automatic basis exists. The record's `synthesize` is a recorded human override of
  that refusal.

Tests pin all four behaviours: accepted admits specified; accepted never admits implemented; an
unaccepted platform device is still refused; `undrivable` still admits an unidentifiable device.

## Two defects found along the way

1. **A refused build wrote into the tree.** `build_service.build()` laid the Makefile, linker
   script and grub config *before* the sources gate refused. Once `play-doom.md` stopped being a
   stub, a packaging test got past `gate_spec` and scaffolded the repo's own `kernels/x86_64`.
   Every tree-dependent test then stopped skipping, giving 13 failures. The sources gate now runs
   first, and `test_a_refused_build_leaves_the_tree_as_it_found_it` pins it.
2. **`timer` was missing from the Doom rule.** doomgeneric calls `DG_GetTicksMs` and `DG_SleepMs`.
   The slice contained `timer` only because the core happens to pull in `kernel/drivers/arch/**`.
   It is now in `requires`, so a service names what it calls.

## Deviations

- **`module-asset` is specified, not mapped.** The plan said "specify and map". The source map's
  header forbids a mapping with nothing behind it (a glob matching nothing turns a refusal into a
  silent omission), and there is no tree. Mapping it would have made the capabilities gate
  *pass* for a capability no image contains. The absent mapping is the honest state until a tree
  implements `pkg_module_asset`.
- **The licence blocker is recorded, not decided.** It was not in the plan. It came up while
  writing the spec, and `licences.yaml` explicitly routes it to a person.

## Validation

| Check | Result |
|---|---|
| `service_spec.py --validate` / `--resolve play-doom.md` | OK; boot, dev, drivers, hal, mm, pkg, slm, sys |
| `driver_spec.py --validate ps2-keyboard.md` | OK, `accepted without a specification: platform:i8042` |
| `driver_strategy.py --device platform:i8042` | REFUSED, all three strategies, unchanged |
| `package_image.py "I want to play Doom" --target qemu-pc.md` | INCOMPLETE, blocked at `[gate: sources]` |
| No WAD and no doomgeneric source in the repo | confirmed |
| agent suite / SLM suite | 1540 passed, 27 skipped / 141 passed |

## What unblocks Doom from here

1. **A generated tree.** That is F6 and V8's job, not this phase's.
2. **The doomgeneric licence decision.** It is a human's call and blocks distribution, not
   implementation.
3. Then implementation of `framebuffer`, `input` and `module-asset`. Each is specified, and the
   host arithmetic for the first two is already proved (`run_display_test.sh`, 21 checks).
