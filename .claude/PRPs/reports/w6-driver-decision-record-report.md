# Implementation Report: Driver Decision Record Format (V2)

## Summary

A target says a device is present; the capability index says whether the tree can drive it.
Neither says how a driver came to exist or how anyone would know it works. `kernel_spec/drivers/`
records that, with `verification` mandatory and mechanical.

This was blocked on D1 and unblocked by it. It now unblocks V4, V5 and with V5 the driver ladder.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | The fields, each justified by the failure it prevents | Complete | 8 fields, no field git owns |
| 2 | `verification` mandatory and executable | Complete | prose refused by name |
| 3 | Two structurally different examples | Complete | second added no field |
| 4 | Validate and refuse | Complete | mirrors `target_spec.py` |
| 5 | Join to the capability index | Complete | reported or refused by `status` |

## The two records

|  | `virtio-net.md` | `e1000.md` |
|---|---|---|
| Strategy | `synthesize` | `port` |
| Basis | `specification` — VIRTIO 1.2 §5.1 | `source` — Intel SDM 317453, with licence position |
| Devices | 3 ids, 2 transports | 1 id, 1 transport |
| Status | `specified` | `implemented` |

They differ on every axis the format claims to express, and `e1000.md` was written second and
**added no field** — the bar `firecracker.md` set for the target format. A test asserts the key
sets are identical apart from the one field each strategy requires.

`virtio-net.md` exists because D7 measured why it must: `drivers.md` `provides` lists exactly one
network driver, so a Firecracker target is refused outright. This record is the first half of
changing that; V5 writes the driver.

## What the format refuses, and why each refusal exists

```
INVALID: nocite.md: strategy 'synthesize' requires 'specification' — a citation, or it means
written from memory
```
Synthesized without a citation is the phantom-device defect with a register map attached.

```
INVALID: prosedrv.md: verification entry 'check that it works on a real machine' is prose. Each
entry must start with 'cmd:' or 'marker:' — a description of how one might check is not a check
```
The mitigations registry already set this bar: *"an image that claims a mitigation it did not
apply is worse than one that declines it, because the claim is the part a user acts on."*
Required even at `status: specified` — a field allowed to be empty until implementation stays
empty afterwards.

```
INVALID: phantomdrv.md: device id(s) in no registry: ffff:ffff. A record cannot claim `probed` —
there is no machine here to have observed anything. Name a real device
```
The one place a driver record is **stricter** than a target. A target may accept an unlisted
device on the strength of `source: probed`; a record has no machine to appeal to.

```
INVALID: impldrv.md: status 'implemented' but vfs has no mapping in source_map.yaml. That
combination claims the driver is in an image that does not contain it. Use 'specified' until it
is written
```
The same false claim `[gate: capabilities]` refuses one level down. `status: specified` with no
mapping is *reported*, not refused — a record for a driver that does not exist yet is the point
of having records, and refusing it would make the format unusable for planning.

## Fields that are not there

No `author`, `date` or `version`. Git records all three, and a field git already owns goes stale
in the file while staying correct in the history. A parameterised test asserts no shipped record
carries one.

## One implementation note

The shared front-matter parser decides list-ness by key name and does not handle inline lists,
so `devices: ["8086:100e"]` arrived as a string and was iterated character by character. Both
forms are now normalised in `driver_spec` — a driver record should look like a service spec
(`requires: [udp, allocator]`), and it sits beside one in `kernel_spec/`. Normalised locally
rather than in the shared parser, which targets also use and which has no reason to change.

## Validation

1295 unit tests pass (was 1259), 111 SLM tests. 36 new tests. Mutation-tested:

| Mutation | Tests failed |
|---|---|
| prose verification accepted | 1 |
| strategy basis not required | 3 |
| implemented-with-no-mapping allowed | 1 |
| specified-with-no-mapping refused too (too strict) | 4 |
| a phantom device id accepted | 2 |
| unavailable registry treated as valid | 1 |
| empty `devices` allowed | 1 |

The fourth is the one worth noting: the format is tested against being too strict as well as too
lax, because a format that refuses a record for an unwritten driver cannot be used to plan one.

## Files

| File | Action |
|---|---|
| `agent/kernel_spec/drivers/README.md` | CREATED — 78 lines |
| `agent/kernel_spec/drivers/virtio-net.md` | CREATED |
| `agent/kernel_spec/drivers/e1000.md` | CREATED |
| `agent/tools/driver_spec.py` | CREATED |
| `agent/tests/unit/test_driver_spec.py` | CREATED — 36 tests |

## Acceptance

- [x] Every field justified by the failure its absence causes; no field git already owns
- [x] `verification` mandatory and executable, including for `status: specified`
- [x] Two structurally different records, the second adding no field
- [x] Both id forms admitted; a device absent from every registry is refused by name
- [x] A missing registry yields unverifiable, never valid
- [x] `status: implemented` with no source mapping refused; `status: specified` reported
