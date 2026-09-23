# Plan: Manifest to Service Spec (intent-C)

**Source PRD**: `auton-intent-to-os-compiler.prd.md` — phase C
**Complexity**: Small — a handoff between two formats that both already exist
**Depends on**: intent-B (landed), F2 (landed)

## Summary

intent-B turns a sentence into a capability manifest. F2 defined the service-spec format the
factory consumes. Nothing connects them. This is the join, and it is explicitly a **handoff,
not an implementation** — it emits the factory's existing format rather than inventing one.

## Evidence

- `agent/tools/intent_manifest.py` — emits `requires`/`excludes`/`assets`/`markers`/`assumptions`.
- `agent/kernel_spec/services/README.md` — the target format: `service`, `requires`, `excludes`,
  `entry`, `markers`, `assets`. Six fields, validated by `service_spec.py`.
- The two formats already share `requires`, `excludes`, `assets`, `markers`. The gap is
  `service` (a name) and `entry` (the serve loop).
- `.claude/PRPs/reports/w2-intent-to-manifest.md` — round-tripping found a real bug in a
  hand-written manifest. The same discipline applies here.

## Tasks

### Task 1: Emit a service spec
- **Action**: `intent_service.py` takes a manifest and writes `kernel_spec/services/<name>.md`
  with front-matter and a prose skeleton. `service` comes from the matched rule name; `entry`
  from a per-intent convention (`<name>_serve`).
- **Gotcha**: `service_spec.load()` rejects an empty `markers`, a filename/name mismatch, and
  unknown capabilities. Emit into a temp path and validate before writing, so a bad emission is
  never left on disk looking authoritative.
- **Validate**: every generated spec passes `service_spec.py --validate` and resolves.

### Task 2: Do not invent prose
- **Action**: The generated spec carries front-matter plus a stub body that says explicitly it
  is generated and what a human must fill in. It must not fabricate protocol behaviour.
- **Why**: `dhcp.md` cites RFC 2131 normatively. A generator that writes plausible-looking
  protocol prose produces a spec an agent will implement confidently and wrongly — the same
  failure as a phantom PCI id, one layer up.
- **Validate**: the stub is unmistakable; a test asserts it contains no protocol claims.

### Task 3: Round-trip
- **Action**: Generate from `"I want to play Doom"` and compare against a hand-written spec for
  the same purpose. Resolve each difference in writing.
- **Validate**: the generated spec and the hand-written `dhcp.md` resolve to comparable slices
  for comparable intents.

## Acceptance
- [ ] A manifest emits a service spec that `service_spec.py` validates and resolves
- [ ] A spec failing validation is never written to disk
- [ ] The generated body is an explicit stub, fabricating no protocol behaviour
- [ ] Differences against a hand-written spec are resolved in writing
