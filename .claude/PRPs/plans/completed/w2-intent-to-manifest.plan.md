# Plan: Intent to Capability Manifest (intent-B)

**Source PRD**: `.claude/PRPs/prds/auton-intent-to-os-compiler.prd.md` — phase B
**Complexity**: Small — the capability index makes it mostly a lookup
**Depends on**: intent-A (landed)
**Unblocks**: intent-C (manifest to service spec), `AUTON train "..."`

## Summary

`AUTON train "I want to play Doom" --output ./Doom` needs a sentence turned into
`requires`/`excludes`/`assets`/`markers`. Today both manifests in `SLM/manifests/` are
hand-written.

This is the compiler's front end. It is small because intent-A did the hard part: the
capability vocabulary exists, slices are computable, and contradictions are already refused
with a path.

## Evidence

- `SLM/manifests/doom.json` and `webserver.json` — hand-written by a human, and the only two
  that exist. Both were written *before* the capability index, so they use
  `drivers(framebuffer, input)` parenthesised form that `_base_capability()` has to strip.
- `agent/tools/capability_slice.py` — `capability_slice(requires, excludes)` returns a closed
  slice or refuses with the path. 69 capabilities across 15 specs.
- `agent/tools/service_spec.py` — the format intent-C emits into; already validates
  `requires`/`excludes` against the index.
- `.claude/PRPs/reports/e2e-intent-scoped-corpus.md` — measured: scoping the *corpus* does not
  improve answer quality, but it does control image content. The manifest's job is the second,
  not the first, and this plan should not be sold on quality.
- The PRD's own open question 4: *"a sentence may not name an input device"* — the manifest
  needs defaults plus a clarifying question.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Refusal with a path | `capability_slice.py` `SliceError` | Say which requirement conflicts, not "invalid" |
| Honest unknowns | `slm.md` rejection reasons | An unrecognised intent is declined by name, never guessed into a default image |
| Manifest shape | `SLM/manifests/doom.json` | `intent`/`requires`/`excludes`/`assets`/`markers` — already consumed by two tools |
| Retrieval over generation | `dev.md` identity section | Capability selection comes from a table keyed on intent, not from the model inventing capability names |

## Tasks

### Task 1: Intent vocabulary, table-driven
- **Action**: A table mapping intent phrases to capability sets — `play doom` ->
  framebuffer/input/module-asset; `host this repo` -> net/http-server; `send and receive
  email` -> net/fs/tcp. Matching is deterministic and the table is data.
- **Why not the model**: a model asked to produce capability names will produce plausible ones
  that are not in the index. The index is the vocabulary and the table is the join. This is the
  same retrieval-not-generation rule that fixed the phantom-PCI-id defect, and the measurement
  behind it is in `e2e-intent-scoped-corpus.md`.
- **Validate**: an intent outside the table is declined with the list of what is known, never
  mapped to a default.

### Task 2: Derive excludes, do not ask for them
- **Action**: `excludes` is computed as the complement: everything the index provides that the
  slice does not reach, reduced to the top-level capabilities worth naming.
- **Why**: a hand-written `excludes` is a guess about what to leave out. A derived one is a
  statement about what was not needed, and it cannot silently omit a capability nobody thought
  of.
- **Gotcha**: the complement is large and mostly uninteresting. Name only excludes that a
  reader would otherwise assume present — `net`, `fs`, `sched`, `ipc` — and record the rest as
  implied.
- **Validate**: the generated Doom manifest excludes at least `net`, `fs`, `sched`, `ipc`; the
  generated webserver manifest excludes `fs` and `sched` but not `net`.

### Task 3: Defaults and the clarifying question
- **Action**: An intent that does not name an input device gets a default (`serial` terminal)
  **and** records that a default was applied. `AUTON train` surfaces it: "assuming serial
  console; add `--input keyboard` for a framebuffer image."
- **Why**: silently defaulting is how an image arrives without the input device its user
  assumed, and the failure appears at boot rather than at build.
- **Validate**: the manifest carries an `assumptions` list; an intent naming its input carries
  an empty one.

### Task 4: Round-trip against the hand-written manifests
- **Action**: Generate from `"I want to play Doom"` and compare against the hand-written
  `doom.json`. Differences are findings about one or the other, resolved in writing.
- **Why**: the hand-written manifests were reviewed by a human and are the only ground truth
  available. A generator that disagrees with both is wrong; a generator that disagrees in a
  *defensible* way means the hand-written one was.
- **Validate**: every difference is classified as "generator wrong", "hand-written wrong", or
  "both defensible", and the file is updated accordingly.

## Validation

```bash
python agent/tools/intent_manifest.py "I want to play Doom"
python agent/tools/intent_manifest.py "I want to host this repo" --output /tmp/web.json
python agent/tools/intent_manifest.py "make me a sandwich"      # must decline, listing known intents
python agent/tools/service_spec.py --validate <generated>       # must resolve
cd agent && python -m pytest tests/unit/test_intent_manifest.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| The table is a keyword matcher dressed as understanding | **M** | It is, and that is correct for now. Declining an unknown intent is the honest behaviour; an LLM front end can be added later behind the same interface |
| Derived excludes are noise | **M** | Task 2 names only the capabilities a reader would assume present |
| Generated manifests drift from the hand-written ones | **M** | Task 4 makes the comparison a required step, not an afterthought |
| Sold as improving answer quality | **L** | It does not, and `e2e-intent-scoped-corpus.md` measured that. This controls image content |

## Acceptance
- [ ] An intent maps to a manifest that `capability_slice` resolves
- [ ] An unknown intent is declined with the known list, never defaulted
- [ ] `excludes` is derived, not hand-supplied, and names the capabilities a reader would assume
- [ ] Applied defaults are recorded and surfaced, not silent
- [ ] Generated manifests reconciled against the hand-written pair, each difference resolved
