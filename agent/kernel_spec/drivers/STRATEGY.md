# Choosing a Driver Strategy

A driver record carries `strategy: reuse | port | synthesize`. This is how one is chosen, and
when none of them is defensible.

## Why this document exists separately from the code

A selector whose criteria live only in a function cannot be argued with. This is a decision about
ring-0 DMA-capable code with no process boundary to contain it, and being argued with is the
point.

## The ordering, and why it is not the intuitive one

From [`auton-driver-development.prd.md`](../../../.claude/PRPs/prds/auton-driver-development.prd.md):

| Option | Optimal for | Costs |
|---|---|---|
| **Reuse** a vetted driver | Correctness, time | Licence constraints; the driver may assume a kernel AUTON is not |
| **Port** from an open driver | Correctness, coverage | Porting bugs are subtle and land in ring 0 |
| **Synthesize** from a vendor spec | Minimality, exact fit, no inherited assumptions | **Nobody has ever run this code** |

Synthesis looks like the natural fit for a project that generates its own OS. It is the most
dangerous option available, because a synthesized DMA programming error is an arbitrary-write
primitive and no prior execution has ever exercised it.

So the default is **reuse > port > synthesize**, and synthesis carries the heaviest verification
burden rather than the lightest.

## Available and preferred are different questions

This distinction is the one the selector exists to hold.

**Synthesize is almost always *available*.** There is usually some document. That is exactly why
availability cannot be the criterion — "we had a datasheet" would justify synthesising every
driver in the tree.

| Strategy | Available when | Preferred when |
|---|---|---|
| `reuse` | A driver exists whose licence permits use here, and which targets a kernel shaped like this one | Always, when available. Nothing beats code that has been run |
| `port` | Source exists under a licence permitting derivative works, and the source's kernel assumptions can be identified | Reuse is unavailable, and the source is small enough that its assumptions can be enumerated |
| `synthesize` | A **normative** specification is inventoried *and ingestable* | Neither of the above, **and** the device is simple enough that the spec is the whole truth — a virtio device, not a modern GPU |

Note what makes `synthesize` available: not "a document exists" but "a normative specification is
inventoried and ingestable". A datasheet nobody can fetch is not a basis; it is a citation.

## What makes each unavailable

| Strategy | Unavailable when |
|---|---|
| `reuse` | No driver, or a licence whose obligations this project cannot meet, or an incompatible kernel shape |
| `port` | No source, or a licence forbidding derivative works, or `licence: unknown` |
| `synthesize` | No specification in [`agent/hardware/vendors.yaml`](../../hardware/vendors.yaml), or one that is inventoried but not ingested |

"Not inventoried" and "not ingested" are different states and the second is actionable —
`vendor_fetch.py` exists. A refusal says which.

## Licences are a table, not a judgement

See [`licences.yaml`](licences.yaml). It records what a licence **requires** — attribution,
source disclosure, same-licence derivative works. It does not characterise what is "safe", and
where the answer depends on how code is combined, the entry says so and the selector refuses
rather than deciding.

`licence: unknown` makes reuse and port **unavailable**, not assumed-fine. An unrecorded licence
is a defect that surfaces at distribution, long after anyone can answer it cheaply.

## Refusing

When no strategy is defensible, the selector refuses and names all three with the reason each
failed. The alternative is a record asserting `synthesize` against a document nobody can fetch —
which validates structurally, and is a lie.

A refusal is a real outcome here. `agent/kernel_spec/drivers/README.md` already admits
`status: undrivable` for the same reason: some devices cannot be driven from any open document,
and saying so is more useful than an empty record.

## What this does not decide

- **Whether a driver should exist at all.** That comes from a target having the device.
- **Whether the result is correct.** That is `verification`, and V9's gate.
- **Whether a human has reviewed it.** A synthesized driver reviewed by nobody must not ship.
