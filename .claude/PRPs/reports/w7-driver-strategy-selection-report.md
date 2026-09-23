# Implementation Report: Strategy Selection (V4)

## Summary

`strategy` was a field in every driver record that nothing decided. `driver_strategy.py` now
chooses one — reuse, port, synthesize, or none — against criteria written down separately from
the code, and refuses when no option is defensible.

Running it against the tree's own records found that `virtio-net.md` cited a specification the
tree had never heard of.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | The criteria, written down before the code | Complete | `drivers/STRATEGY.md` |
| 2 | Licence compatibility as a table | Complete | 11 entries; `unknown` is unavailable |
| 3 | Select, and record why | Complete | every option recorded, not just the winner |
| 4 | Refuse rather than guess | Complete | three availability states |
| 5 | The inventory gap this exposes | Complete | VIRTIO inventoried, not committed |

## The finding

`drivers/virtio-net.md` carries `specification: "VIRTIO 1.2 §5.1"` and `strategy: synthesize`.
`vendors.yaml` inventoried 44 documents across 25 vendors and **not one of them was VIRTIO**. The
record's basis was a document the tree could not fetch, had not ingested, and did not know the
licence of — a citation rather than a basis, and `driver_spec` validated it because a citation is
all the format checks.

The selector refused, which is the correct and inconvenient answer:

```
   synthesize  absent     no vendor 'virtio' in vendors.yaml — nothing records what it publishes
REFUSED: no strategy is defensible for this device.
```

Task 5 inventoried the OASIS specification. The same query now says something actionable:

```
   synthesize  blocked    Virtual I/O Device (VIRTIO) Specification is inventoried but not
                          ingested — run vendor_fetch.py oasis-virtio/virtio-spec
```

It still refuses overall, and should: the document is not in `.cache/`. **V5's `synthesize` cannot
be justified by the selector until the specification is fetched.** That is a real precondition
and it is recorded rather than worked around — fetching is not this phase's job, and the plan's
Task 5 asked only that the document be inventoried.

## Available and preferred are different questions

The distinction the phase exists to hold. Synthesize is almost always *available* — there is
usually some document — which is exactly why availability cannot be the criterion. Three states,
not two:

| State | Meaning |
|---|---|
| `available` | the basis exists, is reachable, and its licence permits this act |
| `blocked` | something exists but cannot be used — and what to do about it |
| `absent` | there is no basis at all |

"Not inventoried" and "not ingested" are different, and the second has a command that fixes it.
Collapsing them would turn an actionable state into a dead end.

## Licences: a table that refuses to be legal advice

`licences.yaml` records what a licence **requires** — attribution, source disclosure,
same-licence derivative works — and never characterises what is "safe" or "compatible". A test
asserts neither word appears anywhere in it.

| Entry | reuse / port | Why |
|---|---|---|
| MIT, BSD-3-Clause, ISC, Apache-2.0 | permitted | obligations are attribution-shaped |
| GPL-2.0-only, GPL-2.0-or-later | **depends-on-use** | the answer depends on how code is combined and what is distributed. The selector refuses and says a human must decide |
| CC-BY-4.0 | not-applicable | a documentation licence — a basis for `synthesize`, never for reuse |
| `unknown` | **unavailable** | not a neutral state. An unrecorded licence is a defect that surfaces at distribution |
| `proprietary` | unavailable | though a spec under such terms may still support `synthesize` — reading a document and writing original code is a different act from copying one |

## Two joins that are tables, not logic

**Device id → publisher.** PCI vendor ids are assigned by PCI-SIG; `vendors.yaml` is keyed by
publisher; neither derives from the other. virtio's ids are registered to Red Hat while its
specification is published by OASIS. Intel's NIC ids and Intel's SDM sharing a name is a
coincidence the join must not rely on, so it is a table.

**Which document kinds are a normative basis.** A device registry tells you a device exists, not
how to program it; a security advisory even less. `pci.ids` is not a basis for writing a driver.

## Two defects found in existing code

`STRATEGY.md` landing in `kernel_spec/drivers/` broke `driver_spec.py --all`, which globbed
`*.md` and excluded exactly one filename. A list of names to skip grows silently wrong the first
time someone adds a third document, so records are now distinguished **structurally** — a record
has front-matter, prose does not.

`driver_spec.load` raised `TargetError` for a malformed driver record, because the front-matter
parser is shared with targets. A caller catching `DriverError` was surprised by it — which is how
the glob bug surfaced as a traceback rather than a skip. Now re-raised as `DriverError`.

## Validation

1364 unit tests pass (was 1339), 111 SLM tests. 25 new tests. Mutation-tested:

| Mutation | Tests failed |
|---|---|
| synthesize preferred over reuse | 1 |
| an uningested spec counts as available | 3 |
| `unknown` licence treated as permitted | 1 |
| GPL decided rather than refused | 1 |
| a device registry counts as a normative basis | 1 |
| an unreadable registry refuses instead of saying undecidable | 1 |

The last is worth naming: on a fresh checkout `.cache/` is empty, and an unidentified device is
not the same as an undrivable one. Refusing every device there would refuse for a reason that is
false, so the selector raises *undecidable* (exit 3) instead.

## Files

| File | Action |
|---|---|
| `agent/kernel_spec/drivers/STRATEGY.md` | CREATED |
| `agent/kernel_spec/drivers/licences.yaml` | CREATED — 11 entries |
| `agent/tools/driver_strategy.py` | CREATED |
| `agent/tests/unit/test_driver_strategy.py` | CREATED — 25 tests |
| `agent/hardware/vendors.yaml` | UPDATED — `oasis-virtio`, 45th document |
| `agent/tools/driver_spec.py` | UPDATED — `records()`, error type fixed |
| `agent/kernel_spec/drivers/README.md` | UPDATED — the strategy section |

## Acceptance

- [x] Criteria written down and justified by the security argument, not convenience
- [x] *Available* and *preferred* are separate questions, and the document says so
- [x] Licence compatibility is a table; `unknown` makes reuse and port unavailable
- [x] A selection cites the inventory entry that justified it
- [x] No defensible option produces a refusal naming all three and why each fails
- [x] "Not inventoried" and "not ingested" are distinguished
- [x] The VIRTIO specification is inventoried, and not committed
