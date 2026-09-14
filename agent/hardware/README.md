# Hardware vendor inventory

What silicon documentation exists, per vendor: where, under what licence, at what cadence, in
what form, and what key its errata are indexed by. [`vendors.yaml`](vendors.yaml) is the data;
[`../tools/vendor_inventory.py`](../tools/vendor_inventory.py) validates it and reports
coverage.

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
INVALID: refusing to plan a fetch into 'agent/hardware/docs': it is tracked, and
4 of intel's documents are not redistributable (intel-sdm, intel-spec-update,
intel-sa). Ingest and derive; never vendor the source. Use an untracked cache
such as .cache/vendor/.
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

Three vendors have nothing available: Qualcomm, Apple, MIPI. Six more publish documents but no
errata. A coverage report that omitted them would overstate what AUTON can check.

## Inventoried is not ingested

Every record here says a document *exists and is reachable*. None says it has been fetched,
parsed or normalised. `--coverage` prints both numbers and they are currently 28 and 0.

The PRD's success metric — "≥6 vendors with an ingestion pipeline" — measures the second. H2
(Intel, AMD) and H3 (Arm, RISC-V) do that work, and both are gated on H0 (shell hardening),
because pointing agents at externally fetched documents while they hold a shell is the
combination that turns a vendor PDF into code execution.

## Refreshing

`cadence` says how often each document changes. Intel's Specification Updates are monthly and
are the ones that matter most — an erratum list six months stale is worse than none, because it
reads as current.

A refresh re-fetches into `.cache/vendor/`, re-derives the normalised records, and diffs them.
The diff is the interesting artifact: a new erratum row appearing in a Specification Update is
exactly the event H10's conformance checking exists to act on.
