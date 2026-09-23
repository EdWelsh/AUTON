# Implementation Report: Probe Ingest (D4)

## Summary

D2 derives a target from an AUTON host's provenance; D3 from a hypervisor's machine type. Bare
metal is the class where nothing is decided and nothing can be derived, so the only honest source
is the machine itself. `probe_ingest.py` turns pasted `lspci -nn`, `/proc/cpuinfo` and
`dmidecode` output into a target with `source: probed` on every fact it supports.

`qemu-pc.md` has claimed `source: probed` since D1 while being written by hand. This is the tool
that makes the claim true rather than asserted — and the round-trip proves it: probing a QEMU
guest reproduces that file's device block **exactly**.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Parse `lspci -nn` | Complete | ids and class codes only; unparsed lines shown |
| 2 | Parse `/proc/cpuinfo` into silicon | Complete | taken already-folded; cross-checked |
| 3 | Parse `dmidecode`, refuse to guess the class | Complete | identifying fields stripped |
| 4 | Partial input is partial, not wrong | Complete | refused naming three fields |
| 5 | Probed facts are the only ones that may say `probed` | Complete | round-trip exact |

## The three things it will not do

**It does not keep the names `lspci` prints.** Those come from the *host's* `pci.ids`, which may
be a different revision from the ingested one. Capturing them would put an unattributed second
source of truth into the record. Ids and class codes only; the name is looked up through
`device_registry.identify`, which cites its document.

**It does not keep serial numbers, UUIDs or asset tags.** `dmidecode` reports all three. A target
definition is a file that gets committed, and none of it is needed to build an image. Stripped at
parse time, and the omission is recorded in the document — an omission nobody mentions reads as
an omission nobody noticed.

**It does not guess the machine class.** `Acme Robotics Ltd` is not evidence of bare metal; it may
be a hypervisor the table has not seen. Guessing `bare-metal` would make D6's bare-metal rules
fire wrongly, and guessing `vm` would suppress them. `class` is left unset, a note records why,
and the definition is refused naming it.

## The trap, and how it is held down

`/proc/cpuinfo` reports `cpu family`, `model` and `stepping` **already folded**, in decimal.
`errata_table.Signature.from_cpuid` exists for a raw CPUID `eax` and folds extended family/model.
Applying it here would fold twice and silently produce a different machine — a Core i7-8650U
(family 6, model 142) would become something else, and `errata_table` would then answer
confidently about silicon nobody has.

The test cross-checks both routes to the same triple: `Signature.from_cpuid(0x806EA)` must give
`(6, 142, 10)`, which is what the cpuinfo states. Mutating the parser to re-fold fails 3 tests.

## Task 5: the round-trip

The device block is byte-identical to the hand-written `qemu-pc.md`:

```
$ diff <(qemu-pc.md devices) <(probed devices)
identical
```

One difference had to be resolved first. `lspci` reports `8086:7000` with class `0601`, and base
class `06` covers every kind of bridge, so it came out `host-bridge` where the hand-written file
says `isa-bridge`. `pci-classes.yaml` gained a `subclasses` map with exactly one entry — added
because the round-trip demanded it, which is the rule `services/README.md` states for adding a
field, rather than because sub-class precision seemed generally nice.

The silicon deliberately still differs: the control records QEMU's default emulated CPU (family 6,
model 6), the probe a real Core i7 passed through. A probe disagreeing with a hand-written file is
exactly what `source` exists to make legible, and a test asserts the disagreement rather than
papering over it.

## Validation

1236 unit tests pass (was 1213), 111 SLM tests. 23 new tests. Mutation-tested; each mutation
asserted to have applied:

| Mutation | Tests failed |
|---|---|
| cpuinfo values re-folded through `Signature` | 3 |
| redaction removed | 1 |
| redaction silent — stripped but not recorded | 1 |
| unparsed lines dropped | 2 |
| unrecognised manufacturer defaults to `bare-metal` | 2 |
| an absent fact filled in with a zeroed default | 1 |
| the device role ignores the class code | 2 |

## Files

| File | Action |
|---|---|
| `agent/tools/probe_ingest.py` | CREATED |
| `agent/kernel_spec/targets/pci-classes.yaml` | CREATED |
| `agent/tests/unit/test_probe_ingest.py` | CREATED — 23 tests |
| `agent/kernel_spec/targets/README.md` | UPDATED — the probing section |

## Acceptance

- [x] `lspci -nn`, `/proc/cpuinfo` and `dmidecode` each parse; unparsed lines are reported with text
- [x] Device ids join to the ingested registry; an unlisted probed device is accepted
- [x] Silicon taken already-folded; a test proves both routes agree
- [x] Serial numbers, UUIDs and asset tags never appear in the output
- [x] An unrecognised manufacturer leaves `class` unset rather than guessing
- [x] Partial input yields a partial target, refused naming `class`, `firmware`, `silicon`
- [x] Every emitted fact says `probed`; nothing inferred does
