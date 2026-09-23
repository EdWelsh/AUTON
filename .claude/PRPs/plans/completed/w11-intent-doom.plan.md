# Plan: I1 Doom (intent-G)

**Source PRD**: `auton-intent-to-os-compiler.prd.md` — phase G
**Depends on**: F (packaging, landed), V7 (framebuffer + input specified)
**Status of its blockers**: four, measured rather than assumed

## Summary

`AUTON train "I want to play Doom" --output ./Doom` is the PRD set's headline intent and has
produced an INCOMPLETE package since the intent existed.

V7 measured what remains, and it is not one thing:

| Blocker | State | Whose problem |
|---|---|---|
| `play-doom` service spec | missing | intent-C's handoff — a format exists, nothing has emitted one |
| `framebuffer` | specified, **not implemented** | needs a tree; V7 removed its phantom mapping |
| `input` | specified, **`status: undrivable`** | needs a **recorded human decision**, not code |
| `module-asset` | specified, **not implemented** | not a driver problem — the WAD is a boot module |

This plan sequences them. Three are ordinary work; the third is a decision someone has to take
deliberately, and this plan's most useful output may be forcing that rather than coding around it.

## Evidence

- `.claude/PRPs/reports/w8-driver-framebuffer-input-report.md` — the four blockers, each checked
  against the tree rather than assumed. *"Doom is **not** unblocked."*
- `agent/tools/intent_manifest.py:77-79` — the `play-doom` rule:
  `requires=("framebuffer", "input", "module-asset")`, `assets=("doom.wad",)`,
  markers `[FB] mode set`, `[INPUT] keyboard ready`, `[DOOM] frame 1`.
- `agent/kernel_spec/drivers/ps2-keyboard.md` — `status: undrivable`, and why: no inventoried
  specification for the i8042, so *"the verification burden a synthesized ring-0 driver carries
  cannot be discharged the usual way"*. It names the decision needed: accept on
  convention-plus-tests, or find a citable specification.
- `agent/kernel_spec/drivers/framebuffer.md` — `status: specified`, basis
  `gnu-multiboot/multiboot2-spec`, geometry from `boot_info_t`. No VBE call needed.
- `tests/kernel/display_test.c` — 21 host checks already proving the pitch arithmetic and
  scancode translation. The hard parts are proved; what is missing is a tree to put them in.
- `agent/kernel_spec/services/README.md` — the service-spec format `play-doom.md` must satisfy.
- `agent/tools/package_image.py` — produces the package and states the blocker. Its
  `blocked_by` is what this phase must empty.

## Patterns to Mirror

- **State the blockers, do not assume them**: V7's Task 6 checked each against the tree.
- **A decision recorded, not coded around**: `ps2-keyboard.md` exists precisely so someone makes
  the call deliberately.
- **`module-asset` is a boot module, not storage**: `boot.md`'s Multiboot2 module parsing already
  exists; Doom needs no filesystem, which is what makes it the right first intent.

## Tasks

### Task 1: Emit `play-doom.md`, through the handoff that exists
- **Action**: `intent_service.py` emits the service spec from the manifest, as intent-C built it
  to. Fill in the body; the stub marker must be deleted, not left.
- **Gotcha**: `gate_spec` refuses a spec still carrying `STUB_MARKER` — *"its front-matter is real
  and its body is empty; an agent handed one will implement it confidently and wrongly."* The
  generated stub is a starting point, not the deliverable.
- **Gotcha**: the spec must not restate `drivers.md`. Doom's spec says what Doom does with a
  framebuffer, not how a framebuffer works.
- **Validate**: `service_spec.py --resolve play-doom` computes a closed slice; no stub marker.

### Task 2: Take the input decision, in writing
- **Action**: Decide whether `ps2-keyboard` is accepted on convention-plus-tests or waits for a
  citable specification, and record it in the driver record.
- **Why this is a task and not a detail**: it is the one blocker no amount of code removes.
  `undrivable` was written so the decision is taken deliberately rather than by someone quietly
  changing `strategy` to `synthesize`.
- **Gotcha**: if the decision is to accept, the record's `status` changes and its `specification`
  must say what it rests on — *"convention plus host-proved scancode translation"* is honest;
  citing a datasheet nobody can produce is not.
- **Gotcha**: if the decision is to wait, **Doom stays blocked** and this plan says so rather than
  substituting a different input path to look productive.
- **Validate**: the record carries the decision and its reasoning, whichever way it went.

### Task 3: `module-asset` — the WAD as a boot module
- **Action**: Specify and map `module-asset`: Multiboot2 module parsing already lands modules in
  `boot_info_t.modules`, so this is the consumer.
- **Why it is the easy one**: no filesystem, no driver, no vendor document. `boot.md` parses the
  modules already; nothing reads them for an asset.
- **Gotcha**: `doom.wad` is **copyrighted and must never be committed**. The same rule
  `vendor_inventory.fetch_plan` enforces for vendor documents applies — the asset is handed in at
  build time from a path the user supplies, and `package_image.py` already records assets by name
  rather than embedding them.
- **Validate**: a manifest requiring `module-asset` resolves; no WAD in the tree; `.gitignore`
  covers the asset path.

### Task 4: Say what is still missing, again
- **Action**: Re-run the package and record the remaining `blocked_by`, as V7 did.
- **Why**: three of four blockers are addressable here and the fourth may not be. A phase that
  ends with "Doom works" without checking is how the PRD acquired an INCOMPLETE package it
  believed was nearly done.
- **Gotcha**: `framebuffer` being *specified* does not make it *implemented*. Without a generated
  tree there is no `kernel/drivers/fb/framebuffer.c`, and `[gate: capabilities]` will refuse —
  correctly. That refusal is the honest end state of this plan if F6/V8 have not produced a tree.
- **Validate**: the report states the remaining blockers by name, or states that there are none
  and the image boots.

## Validation

```bash
python agent/tools/intent_service.py "I want to play Doom"
python agent/tools/service_spec.py --resolve play-doom
python agent/tools/driver_spec.py --validate agent/kernel_spec/drivers/ps2-keyboard.md
python agent/tools/package_image.py "I want to play Doom" --output /tmp/doom \
    --target agent/kernel_spec/targets/qemu-pc.md
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| The input decision is made by quietly changing `strategy` | **H** | Task 2 requires it recorded with reasoning; `driver_spec` refuses an uncitable `synthesize` |
| Doom is declared unblocked without a boot | **H** | Task 4 re-runs the package and reports `blocked_by` |
| `doom.wad` is committed | **H** | Task 3's gotcha; assets are recorded by name, never embedded |
| The service spec restates the driver spec | **M** | Task 1's second gotcha; `services/README.md` rule 1 |
| The phase ends blocked on a tree and reads as failure | **M** | It is the honest end state and Task 4 names it. F6 and V8 are what produce a tree |

## Acceptance
- [ ] `play-doom.md` exists, resolves to a closed slice, carries no stub marker
- [ ] The input decision is recorded in the driver record with its reasoning
- [ ] `module-asset` is specified and mapped; no copyrighted asset in the tree
- [ ] The package is re-run and the remaining blockers stated by name
- [ ] If Doom is still blocked, the report says so rather than substituting a nearby success
