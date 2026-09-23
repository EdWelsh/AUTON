# Implementation Report: Derive an AUTON-Hosted Target (D2)

## Summary

The recursive case — a guest hosted on an AUTON image another kernel team built. It is the one
target that is perfectly knowable, because the host was built from a manifest and wrote down what
it is, so the derivation probes nothing and asks nothing.

The plan called this out as two steps, and it was right: packaging never recorded what it built
*for*, only what the image was *for*. That had to land first.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Packaging records its target | Complete | `--target`; an image without one says so |
| 2 | Host image to guest target | Complete | keyed on the host image's sha256 |
| 3 | The honest limit | Complete | a Doom host yields a guest with nothing |
| 4 | Errata inheritance, asked not answered | Complete | recorded as open |

## What the derivation found

**Copying a fact was strengthening it.** The first working derivation carried host silicon down
and stamped `source: derived` on it unconditionally. For a host that had only *assumed* its
silicon, that turns a guess into a derived fact purely by being read — the exact defect `source`
exists to prevent. Deriving from an assumption yields an assumption; a probed host fact becomes
`derived`, an assumed one stays `assumed`.

**No host in this tree can host anything.** Deriving from a real DHCP package refuses:

```
INVALID: host: the host package has no image.iso (no service spec for 'serve-dhcp'.
intent_service.py can emit a stub, but a stub is not implementable). A package that produced no
image cannot host anything, and a guest target derived from it would name a host that does not
exist
```

That refusal is correct and it is also the honest state of the tree: `kernels/` was removed, and
`serve-dhcp` has no service spec, so no AUTON ISO exists to derive from. The end-to-end path is
therefore exercised against a **constructed** host package whose shape matches what
`package_image.py` writes — real manifest, real provenance shape, a stand-in ISO with a real
sha256. The tests say so in the fixture's docstring rather than implying a build happened.

## Task 1: packaging records its target

`Package.target` defaults to a statement, not an absence:

```json
{"stated": false,
 "why": "no target was stated; this image was built for no machine in particular,
         and nothing here records what it assumes"}
```

An absent field and a deliberate "no machine in particular" are different claims and a reader
cannot tell them apart. A stated target is **validated before anything is copied** — the same
"nothing invalid reaches disk" rule intent-C enforces — and recorded with every fact's `source`
intact, plus its `absent` list.

## Tasks 2–3: what a host presents

| Host intent | Host requires | Guest devices | Guest `absent` |
|---|---|---|---|
| hand out addresses | net, ipv4, udp | `virtio-mmio:1` network | storage — host excludes `fs` |
| I want to play Doom | framebuffer, input | **none** | network — excludes `net`; storage — excludes `fs` |

The mapping is keyed on capability, not driver: `e1000` and `virtio-net` both provide `net`, and
what a host presents downward is virtio either way — the guest never sees the host's own NIC.

The guest names its host by hash in `platform.host_image`. Verified: changing the host image
changes the derived target.

## Task 4: errata inheritance

Recorded, not answered. Every derived guest carries:

> errata: a guest runs on the host's silicon, so it is affected by defects the host does not
> mitigate. Applicability is decided per machine (H8) and this is per stack — open, and not
> answered by this derivation

Where the host stated no target, silicon is UNKNOWN — `vendor: unknown`, `source: assumed`, and
an assumption saying so. H8's rule holds: unknown is not folded into safe, and an absent field
cannot be told apart from one nobody looked at.

A third assumption states a limit the format would otherwise hide: **AUTON implements no device
model today**, so a derived guest target states what the host manifest permits, not what a
running host offers.

## Validation

1162 tests pass, 27 skipped (whole unit suite). 34 derivation tests, 20 packaging tests.
Mutation-tested; each mutation asserted to have applied before running:

| Mutation | Tests failed |
|---|---|
| an assumed host fact upgraded to `derived` | 1 |
| a host with no image still derives | 1 |
| excluded capabilities presented anyway | 3 |
| the host image hash left out of the guest | 1 |
| a package with no target omits the field instead of saying so | 1 |
| an invalid target copied without validating | 5 |

## Files

| File | Action |
|---|---|
| `agent/tools/package_image.py` | UPDATED — `--target`, `Package.target`, `_record_target` |
| `agent/tools/target_spec.py` | UPDATED — `derive_hosted`, `HOST_PRESENTS`, `ERRATA_QUESTION` |
| `agent/tests/unit/test_target_derivation.py` | UPDATED — 20 → 34 tests |
| `agent/tests/unit/test_package_image.py` | UPDATED — 6 tests added |
| `agent/kernel_spec/targets/README.md` | UPDATED — the recursive case |

## Deviations

The plan's validation commands assume a buildable DHCP host package. None exists in this tree;
the path is exercised against a constructed package, stated plainly above and in the fixture.

## Acceptance

- [x] Packaging records the target it built for; an image without one says so
- [x] A guest target derives from a host package with no questions asked
- [x] The derived target names the host image by hash, and a rebuilt host is detectable
- [x] A host presenting nothing yields a guest with nothing, stated plainly
- [x] Host silicon is carried as `derived`, or `UNKNOWN` — never absent, and never strengthened
