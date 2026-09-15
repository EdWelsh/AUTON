# Build templates

**This is not a kernel.** `kernels/` was deleted because AUTON does not contain one — the
agents build it, per `README.md:11`.

What is here is the *scaffolding a generated tree needs in order to be buildable*: a Makefile,
a linker script, a toolchain fragment and GRUB configs. None of it is kernel source. It is the
part of a tree the factory emits rather than an agent authors, because it is the same for every
image and getting it wrong produces a build failure rather than a bad kernel.

| File | What it is |
|---|---|
| `x86_64/Makefile` | Compiles a source list into `kernel.bin` and an ISO. Takes `CSRC`/`ASRC` from `build_manifest.py`, so it never globs in a generated tree |
| `x86_64/arch/linker.ld` | The memory layout contract `subsystems/boot.md` and `arch/hal.md` specify |
| `x86_64/arch/toolchain.mk` | Cross-compiler flags. Carries the `CC ?=` trap `scripts/lib/toolchain.sh` documents: GNU make predefines `CC`, so `?=` never fires and a bare `make` picks up the host compiler |
| `x86_64/grub/*.cfg` | Multiboot2 boot entries, one with a model module and one without |

## How a tree gets made

`build_service.py --scaffold` copies this into a target directory. The agents then write kernel
source into it against `kernel_spec/subsystems/*.md`; `build_manifest.py` resolves which of those
sources a given manifest needs; and the Makefile compiles exactly that list.

So a generated tree is: **this template, plus agent-authored source, minus whatever the manifest
excludes.**

## Why these are tracked when kernel source is not

A spec is what an agent implements *from*. This is what it builds *with*. Losing it would mean
every generated tree has to re-derive a linker script and a set of freestanding compiler flags —
both of which are unforgiving, arch-specific, and have nothing to do with what the image is for.

The structural record of the retired hand-written tree is in
[`../reference/`](../reference/README.md): 49 files, 183 symbols, their signatures and call
graph. Its *text* is gone on purpose, which is the same rule that retired the tree in the first
place — what is worth keeping from a reference is its structure.
