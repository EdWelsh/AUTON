# Implementation Report: Join a Target to the Errata Table (D8)

## Summary

`machine_safety.py` could already answer "is this machine safe to run this image on". It had
nothing to ask about, because until D1 no file recorded a machine's identity in a reviewable
form. `errata_join.py` is the join, and the errata report is now written into a package before
the build rather than discovered after.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Target silicon to `Identity` | Complete | returns `None`, never a zeroed Identity |
| 2 | Assumed silicon yields UNKNOWN | Complete | the table is not even queried |
| 3 | Report before the build | Complete | `spec/errata.json` in every targeted package |
| 4 | Refuse only the narrow case | Complete — **narrower than planned**, see below |
| 5 | Errata inheritance | Recorded as open | PRD question 4 |

## Task 4: the plan asked for something the data cannot support

The plan called for three conditions: the erratum applies, **the image uses the affected
capability**, and no mitigation exists.

The second is not computable. An erratum record (`vendor_ingest.Record`) carries `applies_to`
identity keys, `status`, `workaround` and `detail` — nothing linking a defect to a capability.
`mitigation_registry.assess` does intersect capabilities, but with what a *mitigation needs*, not
with what an *erratum affects*. Inventing that link would put a confident wrong claim into a
safety report, which is the thing the phase exists to prevent.

So the blocking condition is `unmitigatable` alone: a mitigation record exists and says plainly
that nothing can be done. That is an explicit human judgement someone wrote as
`status: unmitigatable`, not an inference.

Errata with no mitigation record at all are **reported, not blocked**. Measured on real silicon
(family 6, model 151 — covered by the ingested Intel document): **66 applicable errata with no
known mitigation**. Blocking there would make the tool unusable on any real machine.

## Task 2: the case that looks like success

`firecracker.md` records `vendor: unknown, family: 0, source: assumed`, because a microVM guest
inherits the host CPU and cannot read it. Handed to `assess_machine` as-is it produces "nothing
applies" — a clean bill of health for silicon nobody has identified.

```
$ errata_join.py --target agent/kernel_spec/targets/firecracker.md
UNKNOWN: target 'firecracker' rests on assumed silicon (silicon); its vendor/family/model
cannot support a table lookup. No errata verdict can be reached for 'firecracker', and an
unreached verdict is not a clean one.
```

The table is not queried at all. Querying it would produce a verdict, and any verdict about
silicon nobody identified is a false statement. A test asserts the word "safe" never appears.

`silicon_identity()` returns `None`, never `Identity("unknown", 0, 0, 0)` — a valid object that
`assess_machine` will happily answer about. A missing return value cannot be mistaken for an
answer; a zeroed one can. Non-numeric fields return `None` too, never `int()`-with-a-fallback.

## A test that was passing for the wrong reason

Mutating away the `source == "assumed"` check did not fail anything. `firecracker.md`'s vendor is
*also* `unknown`, so a later check masked it, and the assumed-check looked redundant — deletable
by anyone tidying up.

It is not redundant. A target with `source: assumed` and *plausible* values — someone guessing
"probably a Skylake" — would have gone straight to the table and got a confident answer. That is
precisely the shape D5's elicitation will produce. Two tests added for that case; the mutation
now fails.

## Task 5: inheritance, recorded unanswered

Every `auton-hosted` target carries:

> INHERITANCE: this guest runs on host image `abc123def456`, so it is affected by defects in that
> host's silicon whether or not the host mitigates them. The host's own errata assessment is not
> reachable from here — a package records its target, not its host's safety report — so this
> remains PRD open question 4, unanswered. It is recorded rather than omitted, because an
> omission would read as 'no'.

## Incidental: the suite got faster

`errata_table.load` re-parsed a spec-update PDF on every call. The join asks about several targets
against the same document, which took the join's own tests to 30 seconds. Cached by path — a
cached PDF does not change under a running process. **The full unit suite went from 39s to 22s.**

## Validation

1259 unit tests pass (was 1236), 111 SLM tests. 23 new tests. Mutation-tested:

| Mutation | Tests failed |
|---|---|
| assumed silicon queried anyway | **0 → 2** |
| a zeroed `Identity` returned instead of `None` | 1 |
| `int()` with a fallback | 1 |
| applicable errata block the build | 1 |
| `unmitigatable` no longer blocks | 1 |
| the inheritance question dropped | **0 → 2** |

Two survived on first run; both were fixed by widening a test, not by changing the code.

## Files

| File | Action |
|---|---|
| `agent/tools/errata_join.py` | CREATED |
| `agent/tests/unit/test_errata_join.py` | CREATED — 23 tests |
| `agent/tools/package_image.py` | UPDATED — `_record_errata`, `Package.errata` |
| `agent/tools/errata_table.py` | UPDATED — `load` cached by path |

## Deviations

Task 4 blocks on `unmitigatable` alone; the plan's second condition is not computable from the
data and was not faked. Stated above rather than quietly matched.

## Acceptance

- [x] A target's silicon produces an `Identity`, or `None` — never a zeroed one
- [x] Assumed silicon yields UNKNOWN naming the reason, and never the word "safe"
- [x] The report is produced at package time and names the documents consulted
- [x] A build is blocked only on an explicit `unmitigatable`; the third planned condition is not computable and is documented as such
- [x] UNKNOWN errata neither block the build nor count as clear
- [x] Errata inheritance for hosted guests is recorded as unanswered
