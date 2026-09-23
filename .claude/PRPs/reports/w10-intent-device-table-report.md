# Implementation Report: Device Table in the Model File (intent-I)

## Summary

The shipped model knew **four** device ids — `BUS_DEVICES` in `build_corpus.py`, QEMU's default PC
— and invented the rest, measured at 5 phantom citations per 50 novel turns against 0 from a
lookup. Meanwhile 42,101 ingested records sat on the build host where a running image could not
reach them.

The table now lives inside the model file as a section: one artifact, one version contract, no way
for model and table to drift.

| | entries | bytes |
|---|---|---|
| Before | 4 | — |
| Unscoped | **42,101** (21,564 PCI + 20,537 USB) | 2,538,569 |
| Scoped to `qemu-pc` | **7** | 438 |
| Scoped to `firecracker` | **5** | 312 |

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | The section layout, written down first | Complete | `auton_format.py` and `slm.md` |
| 2 | Bump the version, on both sides | Complete | `VERSION = 3`, exact match |
| 3 | Build from the ingested registries | Complete | via `vendor_ingest`, no re-parsing |
| 4 | Scope it | Complete — **by target, not by manifest** |
| 5 | Report what it cost and what it cannot do | Complete | below |

## The PRD's scoping design does not work, and the reason is in the data

The PRD says the table is *"scoped by manifest: a Doom image needs input and display entries, not
every NIC ever made."* That assumes the registry knows each device's class.

**It does not.** `pci.ids` lists `vendor:device → name` in one section and `C 02 Network
controller` in a separate one, with **no mapping between them**. A device's class comes from its
PCI configuration space at enumeration time, not from the registry. A capability-to-class table
would have looked reasonable and scoped nothing.

What *can* scope it is the **target** — the same rule D7 settled for driver selection: a manifest
says what the image is *for*, a target says what the machine *is*. An image built for a known
machine needs that machine's devices plus the devices its drivers bind to. That is 7 entries
instead of 42,101, a 5,800× reduction, and it is derived from data that exists rather than data
that would have been convenient.

## The distinction that nearly got conflated again

Firecracker first scoped to the **full 42,101**. Its devices are all `virtio-mmio:`, which are in
no PCI registry, so its PCI id set is legitimately empty — and `if not target_ids` read that as
*no target stated*.

`None` means nothing was said. An empty set means a target said it has none. Conflating them is
the same defect this project has found in `source_map` (mapped-vs-phantom), in `driver_verify`
(unverified-vs-verified), in `errata_join` (unknown-vs-safe) and in `target_spec`
(unknown-vs-unavailable). Fixed, and it is now 5 entries.

## Where the format grew, and why both sides had to move

The section sits after the tokenizer. An entry is a fixed 12 bytes — `bus`, `vendor`, `device`,
pad, plus a 4-byte offset into one string pool — because the kernel maps this file from a boot
module and runs it **in place**, and a variable-width entry cannot be indexed without walking the
table. The id is two `uint16`s, not text: `8086:100e` as a string costs nine bytes per entry and
turns the binary search into a `strcmp`.

`VERSION` went 2 → 3 in `auton_format.py` **and** in `slm.md`'s `flat_header_t`. The v1→v2 comment
already explained why this is an exact match rather than a minimum, and it was written for
precisely this case: a v2 reader handed a v3 file would parse the table's bytes as further
tokenizer entries — silently wrong rather than loudly broken.

An empty table is still written. A reader must be able to tell *"this image knows no devices"*
from *"this file predates the section"*.

## Two defects found in existing code

`validate()` promises *"Raises ValueError on any mismatch"*. A truncated section raised
`struct.error`, which is not a `ValueError` — a caller catching the documented type would have
missed a corrupt file. Now translated, with the field that was short named.

`SLM/tests/test_auton_format.py::test_validate_rejects_truncated_file` chops three bytes to
truncate the last token. Those bytes are now the device section, so the test was truncating
something else entirely and still passing for a different reason. It passes now because the
contract was fixed rather than the test.

## Against the PRD's stated metric

| Metric | PRD target | Measured |
|---|---|---|
| PCI entries | ≥30,000 | **21,564** |
| USB entries | ≥5,000 | **20,537** |

The PCI target is not reachable from this data and the target was wrong, not the ingestion.
`pci.ids` contains 21,564 *device* records; the remainder of the file is vendor headers and
subsystem entries, which `parse_ids_registry` counts and skips deliberately so an extraction rate
can be reported honestly. Reaching 30,000 would mean counting subsystem rows as devices, which
would inflate the number and make every lookup ambiguous. Reported as short rather than met.

## What this does not do

**The in-kernel lookup is not implemented.** `kernel/slm/neural/loader.c` does not exist and no
kernel tree does. This phase ships the section, the host-side writer and reader, and a `lookup()`
that searches the same sorted order the kernel will — so the exporter and the loader cannot
disagree about ordering. The kernel consumer is specified and unwritten.

A device absent from `pci.ids` is absent from the table. `qemu-pc.md`'s `1234:1111` is QEMU's
invented vendor id, so a scoped image still cannot name its own display device — consistent with
every other layer, which reports it as probed-but-unlisted rather than inventing a name.

## Validation

1461 unit tests, 140 SLM tests (was 111 — 30 new). Mutation-tested:

| Mutation | Tests failed |
|---|---|
| an unsorted table is accepted | 1 |
| duplicates arbitrated instead of refused | 2 |
| the section omitted when empty | 2 |
| the bus dropped from the search key | 1 |
| struct errors escape as `struct.error` | **0 → 1** |
| only one registry read | 1 |
| driver ids dropped from the scoped table | **0 → 1** |

Two survived first time, both test gaps rather than code gaps. The truncation test chopped too
little to reach `struct`, and the scoping test used a target id that was *also* a driver id, so
nothing bound. Both widened.

## Files

| File | Action |
|---|---|
| `SLM/tools/auton_format.py` | UPDATED — layout, `VERSION = 3`, pack/unpack/lookup, `validate` |
| `SLM/tools/build_device_table.py` | CREATED |
| `SLM/tests/test_device_table.py` | CREATED — 30 tests |
| `agent/kernel_spec/subsystems/slm.md` | UPDATED — `flat_header_t` version |

## Acceptance

- [x] The layout is stated in `auton_format.py` and `slm.md`, agreeing field for field
- [x] `VERSION = 3` on both sides; a file with no section is refused naming it
- [x] Built through `vendor_ingest`, never by re-parsing
- [x] Keys strictly ascending; a duplicate is refused, not arbitrated
- [x] Scoped — by target, since the manifest provably cannot; never drops an id the target has
- [x] Entry counts, section bytes and file size reported
- [x] The ≥30,000 target reported against the measured 21,564, with the reason
- [x] The report says the in-kernel consumer is specified and unwritten
