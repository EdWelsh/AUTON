# Plan: Mappings That Point At Nothing (V1a)

**Source PRD**: `auton-driver-development.prd.md` — the half of V1 its report recorded as open
**Depends on**: V1 (landed), V9 (landed)
**Why first in this wave**: V6 and V7 both add a capability whose honest state is "specified, not
implemented". Neither can express that while a mapping to an empty directory reads as implemented.

## Summary

V1 made an *absent* source mapping a build failure. A mapping that points at a directory which has
never existed is not absent — it resolves, matches nothing, and passes every gate.

Measured on a tree without those directories:

```
virtio-blk reported unmapped?  False
files behind kernel/drivers/blk/**:  0
=> the gate passes and the image would contain no block driver
```

That is the same defect V1 exists to prevent, arriving by the one route V1 does not check.

## Evidence

- `agent/kernel_spec/source_map.yaml:29-35` — V1's own report of this, in the file:
  *"DO NOT 'FIX' THEM BY INVENTING MAPPINGS. A path to a directory that does not exist resolves
  without error, because a glob matching nothing is not an error."*
- `agent/kernel_spec/source_map.yaml:78,80` — `framebuffer: [kernel/drivers/fb/**]` and
  `virtio-blk: [kernel/drivers/blk/**]`. Both directories have never existed in this repo.
- `agent/tools/build_manifest.py:108-118` — `resolve()` appends each capability's patterns to
  `wanted_patterns` and only records `unmapped` when `source_map.capabilities.get(cap)` is `None`.
  A pattern list that matches nothing is indistinguishable from one that matches everything it
  should.
- `agent/tools/build_service.py` `gate_capabilities` — consumes `unmapped_capabilities`, so it
  cannot see this case by construction.
- `.claude/PRPs/reports/w6-driver-capability-honesty-report.md` — *"That is a third state between
  mapped and unmapped, and it is the more dangerous one: an invented mapping turns a refusal into
  a silent omission."* Recorded as a follow-on; this is it.
- `agent/tools/driver_verify.py` — V9 established the precedent for a check that reasons about
  what is actually present rather than what is declared.

## Patterns to Mirror

- **Three states**: `target_spec.Identification`, `driver_verify.Outcome`. Mapped-but-empty is a
  value, not a variant of unmapped.
- **Consume, do not recompute**: `gate_capabilities` reads `resolve()`'s report. The new state
  belongs in the same report.
- **A gate explains what to do next**: `GateFailure`.

## Tasks

### Task 1: Report the third state
- **Action**: `resolve()` returns `phantom_capabilities` — capabilities whose patterns are present
  in the map and match no source in this tree.
- **Why in the report**: `gate_capabilities` already consumes that report and a second traversal
  of the tree would drift from the first. The information is free at the point `included` is
  computed.
- **Gotcha**: a capability is phantom only when **every** one of its patterns matches nothing. A
  capability with two patterns, one of which matched, is satisfied — reporting it would fire on
  every partial map and teach the reader to ignore the warning.
- **Validate**: a tree with no `kernel/drivers/blk/` reports `virtio-blk` phantom; the same tree
  with one file under it does not.

### Task 2: Refuse it the way an absent mapping is refused
- **Action**: `gate_capabilities` refuses on a directly-required phantom capability, with a
  message distinguishing it from the unmapped case.
- **Why a different message**: the fix is different. An unmapped capability needs a mapping; a
  phantom one has a mapping that lies, and the reader needs to know which.
- **Gotcha**: transitive capabilities still must not fail the build — the rule V1 established for
  the same reason, that the spec author did not choose the dependency.
- **Validate**: a spec requiring `virtio-blk` against a tree without `kernel/drivers/blk/` is
  refused naming the pattern that matched nothing.

### Task 3: A driver record cannot claim `implemented` over a phantom mapping
- **Action**: `driver_spec.check_status` treats a phantom mapping as no mapping.
- **Why**: `status: implemented` is already refused when `provides` has no mapping. A mapping to
  an empty directory is the same false claim wearing a disguise, and `virtio-blk`'s record is
  about to exist.
- **Gotcha**: `driver_spec` has no tree. The check needs one, so it must be optional — a record
  validates standalone, and the stricter check runs where a tree is known.
- **Validate**: a record claiming `implemented` for `virtio-blk` is refused when a tree is given
  and passes when none is.

### Task 4: Say it in the file that caused it
- **Action**: Update `source_map.yaml`'s header: the two phantom entries are now detected, and
  what a reader should do about them.
- **Why**: the header currently says this state is undetected and out of scope. Leaving that after
  fixing it is how a comment becomes a lie.
- **Validate**: the header names the check and no longer says the state is unrecorded.

## Validation

```bash
python agent/tools/build_manifest.py --tree <a tree without kernel/drivers/blk> \
    --requires virtio-blk       # reports phantom
python agent/tools/build_service.py <spec requiring virtio-blk> --tree <that tree>  # refuses
cd agent && python -m pytest tests/unit/test_build_manifest.py tests/unit/test_build_service.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Every build starts failing on a partial tree | **H** | Task 1's gotcha: phantom only when *every* pattern matches nothing, and only directly-required capabilities refuse |
| The check needs a tree and `driver_spec` has none | **M** | Task 3 makes it optional; a record still validates standalone |
| The two states get merged into one message | **M** | Their fixes differ — a mapping to add versus a mapping that lies |
| It duplicates `resolve()`'s traversal | **M** | Task 1 computes it where `included` is already computed |

## Acceptance
- [ ] `resolve()` reports phantom capabilities, distinct from unmapped
- [ ] Phantom only when every pattern matches nothing
- [ ] A directly-required phantom capability refuses the build, naming the pattern
- [ ] Transitive phantom capabilities do not fail the build
- [ ] `status: implemented` over a phantom mapping is refused when a tree is known
- [ ] `source_map.yaml`'s header no longer says the state is undetected
