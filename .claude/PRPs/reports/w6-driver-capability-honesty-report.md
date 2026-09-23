# Implementation Report: Driver Capability Honesty (V1 + V3)

## Summary

The build advertised driver capabilities it could not deliver. A manifest requiring `nvme`
resolved to a closed slice, passed every gate in the factory pipeline, and produced an image with
no storage driver in it. That is now a build failure.

Nothing was broken. `resolve()` has computed `unmapped_capabilities` correctly all along and put
it in a report field the pipeline never read. So V1 turned out not to be "mark six capabilities
unavailable" but **make existing, correct information load-bearing** — a smaller change and a
more durable one.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Device identification from the registry (V3) | Complete | `device_registry.py`, three outcomes |
| 2 | The capabilities gate (V1) | Complete | `[gate: capabilities]`, before the stub generator |
| 3 | Name the device, not just the capability | Complete with a finding — see below |
| 4 | Record what unmapped means | Complete | 27 across 11 subsystems |
| 5 | Tests | Complete | 10 + 13 tests, mutation-checked |

## The defect, before and after

```
$ build_service.py _gatetest --tree <tree>          # spec requires nvme
REFUSED: [gate: capabilities] the spec requires capabilities this tree cannot implement:
    nvme  — (drivers)   no source mapping
  A slice containing them resolves and builds; the image would simply not contain the
  driver. Add a mapping in source_map.yaml, or remove the requirement.
```

The gate runs **before** the stub generator. Later would be worse than useless: an
unimplementable capability would be papered over by an absence stub and linked into an image that
builds cleanly.

It consumes `report["unmapped_capabilities"]` and never recomputes it. A second copy of
`resolve()`'s rules — `core_provides`, transitive capabilities — would drift, and two rules
disagreeing is worse than either being wrong.

Only **directly required** capabilities refuse. One pulled in transitively and unmapped is a
weaker case: the spec never named it, and refusing would blame the author for a dependency they
did not choose.

## Task 3: the finding

The plan's mock output was:

```
nvme  — NVM Express controller (drivers)   no source mapping
```

That name cannot be produced honestly. The ingested `pci.ids` holds **device records only** —
21,564 `vvvv:dddd` pairs, zero class-code records. `nvme` and `ahci` are PCI class-coded devices,
not single ids, so there is nothing to look up, and writing "NVM Express controller" would mean
the tool inventing a title — the exact defect V3 exists to prevent.

Measured: **no capability that is unmapped today carries a device id.** All four that do
(`e1000`, `e1000e`, `virtio-net`, `virtio-blk`) are mapped. So the friendly-name path never fires
against the shipped map. It is implemented and tested rather than dropped — a capability being
unmapped in future is a live possibility — and a test states the finding explicitly rather than
leaving the dead path to look like an oversight.

What the refusal does name is the **subsystem that promised it**: `nvme — (drivers)`. That tells
the reader which spec advertised something the tree does not deliver.

## Task 1: three outcomes

| Outcome | Meaning |
|---|---|
| `IDENTIFIED` | the registry lists it, with title and document provenance |
| `UNKNOWN` | the registry was read and does not list it |
| `UNAVAILABLE` | no registry was read at all |

The third matters on a fresh checkout: `.cache/vendor/` is gitignored, so a clone has no
registry. Collapsing `UNAVAILABLE` into `UNKNOWN` would report every device in the world as
unlisted, and a gate built on that would refuse every build for a reason that is false.

Verified with the cache moved aside: identification reports `UNAVAILABLE` and says how to
populate the cache, and **the gate still refuses `nvme`**. An unidentifiable device is not a
reason to allow an unimplementable build.

Every identification carries `document_id`, `document_revision` and `sha256` — an answer that
cannot say which revision of `pci.ids` it came from cannot be re-checked when the registry
updates.

`target_spec.py` was refactored to delegate its PCI lookup here rather than keep a second copy.

## Task 4: 27, not 6

| | Plan | Measured |
|---|---|---|
| Unmapped capabilities | 27 | **27** |
| Subsystems | 9 | **11** |

`acpi ahci arch-aarch64 arch-riscv64 arch-x86_64 channels context-switch dependency-resolve devfs
ext2 hotplug init initramfs message-ring module-asset nvme package-install package-registry
preemptive priority-slm processes services sleep-wake slm-command-channel slm-pool vfs writable`

Most of that is correct information, not defects: the map is per-tree and the seed tree never
implemented `ipc`, `sched`, `fs` or `pkg`. `source_map.yaml` now says so at the top, along with
the warning not to "fix" them by inventing mappings.

## One defect deliberately left open

`framebuffer` → `kernel/drivers/fb/**` and `virtio-blk` → `kernel/drivers/blk/**` point at
directories that have never existed. They resolve without error, because a glob matching nothing
is not an error.

That is a **third state between mapped and unmapped**, and it is the more dangerous one: an
invented mapping turns a refusal into a silent omission, which is the defect the gate exists to
prevent rather than its cure. Detecting it requires a tree on disk, which would make the gate
depend on tree contents rather than on the map. Out of scope here, recorded in `source_map.yaml`
and here.

## Validation

1184 unit tests pass, 27 skipped. 111 SLM tests pass. No regressions (1162 before this phase).

Mutation-tested; every mutation asserted to have applied before running:

| Mutation | Tests failed |
|---|---|
| gate removed (always passes) | 7 |
| transitive capabilities also refuse | 1 |
| `UNAVAILABLE` collapsed into `UNKNOWN` | 1 |
| an unknown device gets a made-up title | 1 |
| provenance dropped from an identification | 1 |

## Files

| File | Action |
|---|---|
| `agent/tools/device_registry.py` | CREATED |
| `agent/tests/unit/test_device_registry.py` | CREATED — 10 tests |
| `agent/tools/build_service.py` | UPDATED — `gate_capabilities`, `CAPABILITY_DEVICES` |
| `agent/tools/target_spec.py` | UPDATED — delegates PCI lookup |
| `agent/kernel_spec/source_map.yaml` | UPDATED — what an absent mapping means |
| `agent/tests/unit/test_build_service.py` | UPDATED — 13 tests added |

## Deviations

`gate_capabilities(spec, report)` rather than the plan's `(spec, tree)`. `build()` already calls
`resolve()`; the plan's own risk table says the gate must consume the report rather than
recompute it, and the two-argument form would have called `resolve()` twice.

Task 3 delivers the mechanism but the plan's example output overstated what the registry can do.
Stated above rather than quietly matched.

## Acceptance

- [x] A spec requiring a directly-unmapped capability is refused, naming it
- [x] The refusal names the device where the registry can identify it — no such capability exists today, stated
- [x] A missing registry yields `UNAVAILABLE`, distinct from `UNKNOWN`, and does not disable the gate
- [x] Capabilities satisfied by `core_provides` are never flagged
- [x] Transitively-unmapped capabilities do not fail the build
- [x] `dhcp` and `fileserver` pass the capabilities gate unchanged
- [x] `source_map.yaml` records what an absent mapping means
- [x] No regressions in the full suite
