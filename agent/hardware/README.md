# Hardware knowledge

What AUTON knows about the machines a kernel will run on, and where each fact came from.

| File | What | Built by |
|---|---|---|
| [`vendors.yaml`](vendors.yaml) | the **inventory**: per vendor, which documents exist, where, under what licence, in what form, indexed by what key | by hand and by the Vendor Scout; validated by [`vendor_inventory.py`](../tools/vendor_inventory.py) |
| [`registry/vendors.json`](registry/vendors.json) | the **registry**: every vendor that has held a PCI, USB, x86 CPUID or Arm MIDR identity (5,164), and whether the inventory covers it | derived by [`vendor_registry.py`](../tools/vendor_registry.py) from `pci.ids`, `usb.ids` and Linux's identity tables |
| [`isa/<arch>.json`](isa/) | **instruction availability**: 284 processor models across x86, AArch64, RISC-V, POWER and IBM Z, each with its feature list closed under implication; for x86 also each of Linux's 437 feature bits: CPUID leaf, register and bit where it has one (132 are Linux-defined synthetic flags with no CPUID location) | derived by [`isa_tables.py`](../tools/isa_tables.py) from LLVM's target definitions (for RISC-V also `RISCVProfiles.td`, the profile base each part builds on) and Linux's `cpufeatures.h` |
| [`isa/exceptions.yaml`](isa/exceptions.yaml) | where **silicon disagrees with the documents**: never shipped, removed, fused off, disabled by microcode, undocumented | by hand and by the Spec Reader; every row cited, `verified: false` until checked against the vendor document |
| `erratum-classes.yaml`, `lineage.yaml`, `os-mitigations.yaml` | errata classes, the per-generation Intel specification updates, OS mitigations | |

```bash
python agent/tools/vendor_registry.py --lookup 1d17         # Zhaoxin; no documents yet
python agent/tools/vendor_registry.py --coverage            # 5,164 vendors, how many covered
python agent/tools/isa_tables.py --has haswell fma4         # absent: never-shipped
python agent/tools/isa_tables.py --has alderlake avx512f    # check at runtime: fused-off
python agent/tools/isa_tables.py --cpuid avx512f            # leaf 0x7 subleaf 0, EBX bit 16
```

## A document never proves an instruction is present

Vendor manuals describe extensions that were announced and never built (Intel's FMA4),
and parts lose extensions after release, by fuse, firmware or microcode (AVX-512 on Alder
Lake, TSX on Haswell and Skylake). The same family, model and stepping can differ by BIOS
and microcode revision. So the tables say what *may* be there, and the kernel's
[`cpu`](../kernel_spec/subsystems/cpu.md) spec requires it to use anything beyond the
architecture baseline only after the running CPU reports it.

## The vendor spec agents

Two agents grow this directory, each in a testing-area workspace
(`scripts/vendor_research.py start <run> --goal ...`, output in `.artifacts/hardware/<run>/`):

- **Vendor Scout**: takes a registry vendor with no coverage (`vendor_queue`: CPU vendors
  first), finds what it publishes, fetches candidates (https, allowed hosts only) and
  proposes `vendors.yaml` entries, or a gap saying nothing is public.
- **Spec Reader**: reads a fetched document page by page and derives records (errata,
  instruction exceptions, verifications of `verified: false` rows), each quoting the page
  it cites.

Their checks are mechanical (`check_hardware_record`): a proposal must load as an inventory
entry and add only new vendors and documents; a derived record must cite a cached
document as `<vendor>/<doc_id>` (no absolute paths, no `..`, nothing outside `.cache/vendor/`)
whose payload hashes to the sha256 in its `provenance.json`, and each quote must be on the
integer page it cites. The syntax gate runs the same checks on every changed proposal and
derived file before a reviewer sees it. Fetched text is presented as untrusted data.
The Spec Reader cannot fetch a document with no `fetch_url` (Intel's): an operator caches it
first with `vendor_fetch.py --vendor <v> --id <doc_id> --from-file <path>`, and until then the
Reader reports that row as blocked.
`scripts/vendor_research.py collect <run>` lists what passed; a person merges it.

## Fetching

Documents with a `fetch_url` are downloaded by
[`vendor_fetch.py`](../tools/vendor_fetch.py) into `.cache/vendor/` (gitignored), with
the sha256 recorded as identity. Intel's CDN refuses scripts, so Intel documents still
come in with `--from-file`.

## The rule

**Ingest and derive. Never vendor the source.**

Most silicon specifications are freely *downloadable* and not freely *redistributable*. Intel's
SDM, AMD's Revision Guides, Arm's TRMs, the UEFI and NVMe specs — all obtainable by anyone, none
licensed for us to republish. What may be committed is what we *derive*: a normalised erratum
record citing document, revision, date and page. What may not is the document.

This is enforced, not advised. `vendor_inventory.py --fetch-plan` refuses to target a tracked
path when any of the vendor's documents is non-redistributable:

```
$ vendor_inventory.py --fetch-plan intel --into agent/hardware/docs
INVALID: refusing to plan a fetch into 'agent/hardware/docs': it is tracked, and 10 of intel's documents are not redistributable (intel-sdm, intel-spec-update, intel-spec-update-6). Ingest and derive; never vendor the source. Use an untracked cache such as .cache/vendor/.
```

The check is on the destination rather than on intent, because a repo full of vendor PDFs is a
licensing problem regardless of what whoever added them meant, and it is tedious to undo once
it is in history.

Fetched documents belong in `.cache/vendor/`, which is gitignored.

## Reading a record

```yaml
- vendor: intel
  category: cpu
  identity_keys: [family, model, stepping, microcode_rev]
  documents:
    - id: intel-spec-update
      title: Specification Update (per processor family)
      kind: errata
      scope: per-family
      access: public-download
      redistributable: false
      form: pdf-tables
      cadence: monthly
```

| Field | Meaning |
|---|---|
| `identity_keys` | What an erratum is indexed by. Required, and the reason is load-bearing: without it an erratum can be matched to a *vendor* but not to a *running machine*. CPUID leaf 1 gives family/model/stepping, which is the join column. |
| `kind` | `architecture-manual`, `errata`, `security-advisory`, `microcode-revision`, `register-reference`, `machine-readable-registers`, `device-registry`, `standard` |
| `access` | How it is obtained, from `public-download` through `membership-required` |
| `redistributable` | Must be an explicit boolean. An unclear licence is a blocker, not a default |
| `licence` | Required whenever `redistributable` is true — "we may republish this" needs a reason on record |
| `form` | What a parser will face: `pdf`, `pdf-tables`, `xml`, `c-headers`, `flat-text`, `pdf+source`, `structured` |
| `cadence` | How often it changes, which sets the refresh interval |
| `url_hint` | A hint only. URLs rot; document numbers and titles do not, so identity is `id` plus the vendor's document number |

## Gaps are records too

A vendor with nothing public carries a `gaps` list and no documents, and the validator rejects
a vendor that has neither. Silence would read as coverage:

```yaml
- vendor: apple
  documents: []
  gaps:
    - kind: register-reference
      reason: >-
        No public silicon specifications of any kind. The Asahi Linux project's
        reverse-engineering documentation is the de-facto reference, and carries
        third-party provenance — a conformance finding sourced from it can never
        be stated with the confidence of one from a vendor document.
```

Three vendors have nothing available: Qualcomm, Apple, MIPI. Of the other 34, 27 list documents
but no errata document (many are sources such as `llvm-project` or `qemu`, which have none to
publish). A coverage report that omitted them would overstate what AUTON can check.

## Inventoried is not ingested

Every inventory record says a document *exists and is reachable*; it does not say the
document has been fetched and turned into facts. `vendor_inventory.py --coverage` prints
the inventory (37 vendors, 76 documents). What is actually derived today:

- `pci.ids` and `usb.ids`: fetched and ingested (`vendor_ingest.py`, about 42,000 device
  records) and the source of the registry;
- LLVM's target definitions and Linux's identity and feature headers: fetched and read by
  `isa_tables.py` and `vendor_registry.py` (`vendor_ingest.py` reports "no parser" for
  them, which is expected);
- Intel's Alder Lake specification update (682436): ingested by hand in w2.

Every other document is the Vendor Scout's and Spec Reader's queue.

## Refreshing

`cadence` says how often each document changes. Intel's Specification Updates are monthly and
are the ones that matter most — an erratum list six months stale is worse than none, because it
reads as current.

A refresh re-fetches into `.cache/vendor/`, re-derives the normalised records, and diffs them.
The diff is the interesting artifact: a new erratum row appearing in a Specification Update is
exactly the event H10's conformance checking exists to act on.
