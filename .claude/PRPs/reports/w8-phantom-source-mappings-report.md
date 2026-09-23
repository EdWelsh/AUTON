# Implementation Report: Mappings That Point At Nothing (V1a)

## Summary

V1 made an *absent* source mapping a build failure. A mapping pointing at a directory that has
never existed is not absent — it resolves, matches nothing, and passes every gate. V1's own report
recorded this as the more dangerous of the two and left it open. This closes it.

Measured before the fix, on a tree with no `kernel/drivers/blk/`:

```
virtio-blk reported unmapped?  False
files behind kernel/drivers/blk/**:  0
=> the gate passes and the image would contain no block driver
```

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Report the third state | Complete | `phantom_capabilities`, beside `unmapped` |
| 2 | Refuse it as an absent mapping is refused | Complete | a *different* message, because the fix differs |
| 3 | No `implemented` claim over a phantom mapping | Complete | optional tree check |
| 4 | Say it in the file that caused it | Complete | header corrected |

## Two states, two fixes, two messages

| | unmapped | phantom |
|---|---|---|
| What it means | no entry in the map | an entry matching no source in this tree |
| What to do | add a mapping | **remove** the mapping until the source exists |
| Message | "no source mapping" | "points at nothing … which matches no source in this tree" |

Merging them would have been the easy thing and would have left the reader with the wrong action.
A test asserts the two messages differ, and another asserts a capability that is *both* is reported
once — as unmapped, the more fundamental state.

```
[gate: capabilities] the spec requires capabilities whose source mapping points at nothing:
    virtio-blk  — (drivers)   maps to kernel/drivers/blk/**, which matches no source in this tree
  A glob matching nothing is not an error, so the build would succeed and the image would contain
  no implementation. Remove the mapping until the source exists — an absent mapping refuses
  honestly; one that lies does not.
```

## Phantom only when *every* pattern misses

A capability with two patterns, one of which matched, is satisfied. Reporting it would fire on
every partial map and teach the reader to ignore the warning — which is how a gate stops working
without anyone disabling it.

This is also where a test passed for the wrong reason. The obvious multi-pattern capability to
test with is `serial`, and `serial` is in `core_provides`, which `resolve()` skips *before* the
phantom check. The test asserted something that was never evaluated, and the mutation "fire when
any pattern misses" survived it. Now the test picks a multi-pattern capability that is not
core-provided, asserts it is actually in the slice, and is paired with its opposite so the two
pin the boundary from both sides.

## Task 3: the check needs a tree, so it is optional

`driver_spec` validates a record on its own — it has no tree and should not require one. So the
phantom check runs only when a tree is given:

```
$ driver_spec.py --all                      # standalone
OK e1000.md: port/implemented, 1 device(s), 3 check(s)

$ driver_spec.py --all --tree <tree with no e1000 source>
INVALID: e1000.md: status 'implemented' but e1000 has no mapping in source_map.yaml.
```

A record still validates standalone; the stricter claim is checked where it can be.

## Task 4: the comment that would have become a lie

`source_map.yaml`'s header said this state was undetected and out of scope. Leaving that after
fixing it is how a comment stops being true. It now names the check, states the rule that follows
— *when a capability is specified but not implemented, give it a `provides` entry and **no** entry
here* — and points at `virtio-net` as the worked example.

## Validation

1412 unit tests pass (was 1396). 17 new tests. Mutation-tested:

| Mutation | Tests failed |
|---|---|
| phantom never reported | 2 |
| phantom when *any* pattern misses | **0 → 1** |
| the gate no longer refuses a phantom | 4 |
| transitive phantoms refuse too | 1 |
| both states share one message | 2 |
| the tree check ignored in `driver_spec` | 1 |

## Files

| File | Action |
|---|---|
| `agent/tools/build_manifest.py` | UPDATED — `phantom_capabilities` in the report |
| `agent/tools/build_service.py` | UPDATED — the phantom refusal, `_patterns_for` |
| `agent/tools/driver_spec.py` | UPDATED — optional tree check on `implemented` |
| `agent/kernel_spec/source_map.yaml` | UPDATED — header corrected |
| `agent/tests/unit/test_phantom_mappings.py` | CREATED — 17 tests |

## Acceptance

- [x] `resolve()` reports phantom capabilities, distinct from unmapped
- [x] Phantom only when every pattern matches nothing
- [x] A directly-required phantom capability refuses the build, naming the pattern
- [x] Transitive phantom capabilities do not fail the build
- [x] `status: implemented` over a phantom mapping is refused when a tree is known
- [x] `source_map.yaml`'s header no longer says the state is undetected
