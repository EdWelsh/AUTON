# Decision (open): which Doom engine, under which licence

**Status: open. This blocks distributing a Doom image, not building or testing one.**

`play-doom.md` specifies the service and w11 took it as far as specification allows. What
remains before any image is *distributed* is a licence question, and it is a person's to answer,
not an agent's.

## The question

The usual engine, **doomgeneric**, derives from the original id Software release and is
**GPL-2.0**. `agent/kernel_spec/drivers/licences.yaml` marks GPL-2.0 `depends_on_use: true`,
which by this project's own rule routes it to a human rather than letting the selector decide.

What has to be settled:

1. **Combination.** A GPL-2.0 engine linked into an AUTON image makes the distributed image a
   derivative work. That is a licence obligation on the whole image, not on one file.
2. **The WAD is separate.** The engine's licence says nothing about game data. `doom.wad` is
   never committed here and never distributed: it is supplied at build time
   (`play-doom.md`, `assets: [doom.wad]`). The shareware WAD has its own redistribution terms.
3. **The alternative**, if the answer is no: an engine under permissive terms, or no Doom image.
   "Build it and decide later" is not available, because deciding later means deciding after
   distribution.

## What is NOT blocked

Specifying, generating, building and booting a Doom image **locally** for the PRD's probe (a
non-blank frame and accepted input). Nothing about that distributes the engine. The blocker
applies to shipping an image to anyone else.

## How this gets answered

The owner decides, and the answer is written here with its reasoning. Until then the catalogue's
Doom row says `roadmap` and cites this file — not "coming soon", which would imply the question
is a schedule rather than a decision.
