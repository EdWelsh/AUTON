# Report: Intent to Capability Manifest (intent-B)

**Plan**: `.claude/PRPs/plans/w2-intent-to-manifest.plan.md`
**Source PRD**: `auton-intent-to-os-compiler.prd.md` — phase B

`AUTON train "I want to play Doom"` now produces a manifest. Both manifests in
`SLM/manifests/` were hand-written before this; the compiler's front end exists now.

## Table-driven, deliberately

Matching is a table of phrases to capability sets, not a model. A model asked to produce
capability names produces plausible ones that are not in the index — the same failure that put
a phantom Realtek NIC into answers to questions naming no device, measured at 5 citations per
50 turns (`e2e-intent-scoped-corpus.md`). The index is the vocabulary; the table is the join.
This is the retrieval-not-generation rule applied one layer up.

Five intents: `play-doom`, `host-repo`, `serve-dhcp`, `serve-files`, `identify-hardware`.
Matching is whole-word on a normalised sentence, longest phrase first — so `play doom` beats a
bare `doom`, and `doomsday` matches nothing. A substring match is how an unrelated sentence
acquires an image.

An unrecognised intent is **declined with the known list**, never mapped to a nearest
neighbour. An image that boots and does the wrong thing is found by a user; a refusal is found
at build time.

## Excludes are derived

Nothing in the rule table names an exclude. They are computed as what the slice does not
reach, filtered to the capabilities a reader would otherwise assume present. A hand-written
`excludes` is a guess about what to leave out; a derived one is a statement about what was not
needed, and cannot silently omit something nobody considered.

An exclude implied by a broader one is suppressed — excluding `net` already excludes `tcp`, and
listing both reads as two decisions where one was made.

| intent | requires | excludes |
|---|---|---|
| play-doom | 8 | net, fs, sched, ipc |
| host-repo | 10 | fs, sched, ipc |

## Defaults are recorded

An intent that does not name an input device gets a serial console **and says so**:

```
ASSUMED: input: assuming serial console; pass --input keyboard for a framebuffer image
```

Silently defaulting is how an image arrives without the input device its user assumed, and the
failure appears at boot rather than at build.

## Task 4 found a real bug — in the hand-written manifest

Round-tripping against the reviewed pair produced three differences. Two were style: the
hand-written manifests name *subsystems* (`net`, `dev`), the generator names *capabilities*
(`ipv4`, `pci`). Both resolve to the same subsystem slice, verified.

The third was a defect. `webserver.json` required `net` wholesale. But `tcp`, `http-server` and
`dhcp-client` are **optional** capabilities of `net`, and an image that does not ask for them
does not get them:

```
hand-written webserver image:
   http-server    ABSENT
   dhcp-client    ABSENT
   tcp            ABSENT
```

...while the same file's markers claimed `[NET] dhcp bound` and `[HTTP] listening on 80`. The
manifest described an image that could not do what its own acceptance markers asserted.

`webserver.json` is corrected and a test pins it. This is exactly what the plan's Task 4 was
for, and it is the first concrete payoff from intent-A's `optional` field — which only earns
its keep when something notices an optional capability was never requested.

## One consumer disagreement, resolved

The two consumers of a manifest wanted different granularity. `build_corpus.py` tags records
with subsystem-level capabilities (`net`, `fs`) and compared them against the manifest's raw
strings; `capability_slice` works at capability level. A capability-level manifest would have
silently dropped every corpus record.

`build_corpus.Manifest` now resolves capability names to their owning subsystems through the
index, so one manifest format serves both. Verified byte-identical corpora from the
hand-written and generated manifests for both images — 187 records for Doom, 443 for webserver.

The resolution degrades safely: if the spec index is not importable, it falls back to the raw
tokens rather than failing, so corpus building never hard-depends on the agent package.

## Acceptance

- [x] An intent maps to a manifest that `capability_slice` resolves
- [x] An unknown intent is declined with the known list, never defaulted
- [x] `excludes` is derived, names what a reader would assume present, and suppresses implied entries
- [x] Applied defaults are recorded and surfaced
- [x] Generated manifests reconciled against the hand-written pair, each difference resolved —
      two as style, one as a bug in the hand-written file
- 27 tests

## Follow-on

- Five intents is a small table. It will need extending, and the honest failure mode is
  declining a reasonable sentence — which is visible, unlike guessing.
- An LLM front end can sit in front of `match_intent` later without changing anything
  downstream, provided it emits a rule name rather than capability names.
- `identify-hardware` is the smallest image the table produces and is the natural first target
  for end-to-end generation, ahead of Doom.
