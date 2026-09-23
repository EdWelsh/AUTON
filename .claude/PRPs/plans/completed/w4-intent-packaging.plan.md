# Plan: Packaging (intent-F)

**Source PRD**: `auton-intent-to-os-compiler.prd.md` — phase F
**Depends on**: intent-C (landed), intent-E (landed)

## Summary

`<output>/` should contain the bootable ISO, an installer, the scoped model and its manifest,
the generating spec subset, and a **provenance record** — which agent or tool wrote which file,
and which spec section each implements.

The PRD's stated reason: *"A human must be able to review generated kernel code without reading
it blind."*

## Evidence

- `agent/tools/intent_manifest.py` produces a manifest from a sentence.
- `agent/tools/intent_service.py` produces a service spec from a manifest.
- `agent/tools/build_service.py` produces an image, with four gates and a leakage measurement.
- `SLM/tools/build_corpus.py --manifest` produces a scoped corpus; `train.py`/`export_auton.py`
  produce the model.
- Nothing assembles these, and nothing records provenance.

## Tasks

### Task 1: The output layout
- **Action**: `AUTON train "<intent>" --output <dir>` assembles: `image.iso`, `model/`,
  `spec/` (the manifest, the service spec, and the subsystem specs in the slice), `install.sh`,
  `PROVENANCE.json`.
- **Validate**: every file is present or explicitly recorded as absent with a reason.

### Task 2: Provenance that is checkable
- **Action**: For each artifact: what produced it, from what input, at what version, with what
  hash. For the spec subset: which sections the slice selected and why.
- **Why**: "a human must review generated code without reading it blind" means the record has to
  say *which spec section this file implements*. Anything less is a file listing.
- **Validate**: the record identifies the tool, input hash and output hash for every artifact,
  and a modified artifact is detectable.

### Task 3: Say what is missing
- **Action**: An intent whose image cannot be built yet (no framebuffer driver for Doom) must
  produce a package that **says so**, not a partial directory that looks complete.
- **Why**: this is the PRD's own leakage argument applied to packaging — an output directory
  missing its ISO looks like a build that half-worked rather than one that was never possible.
- **Validate**: an unbuildable intent yields a package whose status is explicit and whose
  summary names the blocker.

## Acceptance
- [ ] `--output <dir>` assembles ISO, model, spec subset, installer and provenance
- [ ] Provenance names the tool, input and output hash for every artifact
- [ ] The spec subset is the slice, and the record says which sections and why
- [ ] An unbuildable intent produces an explicit incomplete package, never a partial one
