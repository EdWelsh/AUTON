# Report: Packaging (intent-F)

**Plan**: `.claude/PRPs/plans/w4-intent-packaging.plan.md`
**Source PRD**: `auton-intent-to-os-compiler.prd.md` — phase F

The intent chain now terminates in a directory a person can review:

```
$ package_image.py "hand out addresses" --output ./dhcp-image --service dhcp
COMPLETE: ./dhcp-image
  spec/manifest.json            460 B   intent_manifest.py
  spec/subsystems/*.md       (8 specs)  capability_slice.py
  spec/dhcp.md                7,752 B   authored
  image.iso               8,261,632 B   build_service.py
  install.sh                    969 B   package_image.py
```

## Provenance is a review aid, not a file listing

The PRD's reason is specific: *"a human must be able to review generated kernel code without
reading it blind."* That sets the bar above hashes. Every artifact records what produced it,
from what input, and **which spec section it implements**:

```
image.iso — the bootable image; entry dhcp_serve
            sha256 245313429c5fe759, from dhcp.md + 26 sources
```

And every subsystem spec in the subset says why it is there:

```
drivers.md  included because it provides e1000, input, serial, timer
hal.md      included because it provides arch
```

A subsystem present only as a transitive dependency says that instead, rather than claiming a
capability nobody asked for.

The leakage measurement travels with the package, so a reviewer does not have to rebuild to
learn whether the image contains what its manifest excluded: `leaked_symbols: 0, conclusive:
true`.

## An unbuildable intent produces an explicit package

```
$ package_image.py "I want to play Doom" --output ./doom
INCOMPLETE — no service spec for 'play-doom'. intent_service.py can emit a stub,
but a stub is not implementable.
```

The directory contains the manifest and the full spec subset — which is the useful part, because
it says what the image *would* contain — and a README whose "What is missing" section explains
itself:

> It is recorded as incomplete rather than shipped as a partial directory, because a directory
> missing its ISO looks like a build that half-worked rather than one that was never possible.

Doom is blocked on a framebuffer driver that does not exist. That is a real gap, and the
package says which one.

## The installer refuses by default

`install.sh` writes an ISO to a block device, which erases it. So it requires a target
argument, requires the target to be a block device, and requires the operator to **type the
device path a second time**. No default, no `-y`, and the size of what is about to be written is
printed before the prompt.

Two tests exercise the refusals, because an installer nobody has tried refusing is an installer
that erases the wrong disk once.

## A bug the tests found

`package()` created the output directory before matching the intent, so a declined sentence left
an empty `out/spec/` behind. That is the same rule intent-C enforces — nothing invalid reaches
disk — violated one layer up. An empty package directory looks like a build that produced
nothing rather than one that never started. The intent is now matched first.

## Acceptance

- [x] `--output <dir>` assembles ISO, spec subset, installer and provenance
- [x] Provenance names the tool, input and output hash for every artifact
- [x] The spec subset is the slice, and the record says which sections and why
- [x] An unbuildable intent produces an explicit incomplete package
- [x] **The scoped model** — `--train` runs the scoped-corpus pass and packages the result
- 19 tests

## `AUTON train` is now literally true

```
$ package_image.py "hand out addresses" --output ./dhcp --service dhcp --train
COMPLETE  (2m12s)
  image.iso              8,261,632 B
  model/auton-slm.bin   24,664,844 B   trained on the scoped corpus, 3000 steps
  model/manifest.json          460 B
  spec/…                   (9 specs)
  install.sh
```

The model's manifest is copied **beside the model**, not only into `spec/`. A model whose scope
nobody can look up is a model nobody can trust, and the two should not be separable by copying
one file out of the directory.

Training failure is a note, never an exception. An image without a model is a worse image, not a
failed package — and the README says which one it is, because the difference is what the image
can answer: *"falls back to the kernel's rule engine, which answers device and system questions
but not free-form ones."*

The end-to-end run is a test, marked `slow` and run separately, that trains, builds, packages
and then **validates the exported model against the flat-format reader**. A packaged model
nobody parsed is a 24 MB file with a plausible name.

### Two bugs found while wiring it

**The model was packaged after the build stage**, so an incomplete package never got one —
even though a model is scoped from the manifest, which exists for every intent, buildable or
not. Doom cannot be built and can still have a model.

**The absence note said "supplied with --model" when nothing was supplied.** A default string
that describes a path not taken is worse than no note, because it reads as an explanation.

## Follow-on

- Packaging should invoke the scoped-corpus training run rather than taking a model as an
  argument. That makes `AUTON train "<intent>" --output <dir>` literally true, which is the
  shape the whole PRD is named for.
- `install.sh` writes a whole-disk image. An installer that partitions and preserves an existing
  system is a different, larger thing, and the current one should not be mistaken for it.
- The Doom package is the most useful artifact here: it states precisely what is missing, and
  that is the list intent-G has to close.
