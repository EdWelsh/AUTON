# Report: The Unmitigated Sweep (H12)

**Plan**: `plans/completed/w13-hardware-unmitigated-sweep.plan.md` · **Commit**: `7c5e511`

## The count

`intel/intel-spec-update` (12th Gen Core, ADL): 94 errata.

| Bucket | Count | Meaning |
|---|---|---|
| vendor-fixed | 22 | Intel marks it Fixed for the covered steppings |
| removed | 6 | withdrawn ("Erratum has been removed", N/A) |
| vendor-workaround | 15 | Intel documents a workaround ("None identified" does not count) |
| os-mitigated | 0 | a person confirmed an OS mitigation with a URL |
| pending-review | 0 | an unreviewed search hit |
| **documented-unmitigated** | **51** | No Fix, no vendor workaround, none found in Linux or FreeBSD |
| not-checked | 0 | no evidence collected |

`sweep.py --document intel/intel-spec-update --list` prints the 51.

## Method and limits (the count means exactly this)

- **Search**: GitHub code search for the erratum id and its exact title, in `torvalds/linux` and
  `freebsd/freebsd-src`, on 2026-09-22. 94 × 2 × 2 queries, paced to the rate limit.
- **Windows is not checked** and never counted: it has no searchable source.
- **Exact-phrase search misses workarounds that don't name the erratum.** Linux often names a
  quirk by symptom or model, not by Intel's id. So "none found" is a lower bound on evidence, not
  proof of absence. The bucket's `why` always says where and when it was searched.
- **One hit, reviewed and rejected**: ADL038 in `tools/perf/pmu-events/…/alderlake/cache.json`.
  perf tags the affected events with `"Errata": "ADL038"`, which acknowledges the inaccuracy
  and does not work around it. Recorded as `kind: rejected` with its reason; a rejected hit
  counts as searched.
- A mitigation claim without an `evidence_url` is refused when the file loads (`EvidenceError`).
- Nothing was copied from either tree. Only code *locations* are recorded.

## Ingest improvement it needed

`vendor_ingest` now reads each erratum's Problem/Implication/Workaround text: 94 errata, 91 with
detail, 53 with a workaround field (the 3 without detail are removed errata).

## Tests
`agent/tests/unit/test_sweep.py`, 9 cases: bucket rules, "None identified" is not a workaround,
not-checked never merges with none-found, Windows is never claimed, a claim without a source is
refused, a rejected hit counts as searched. Suite: 1610 agent passed, 153 SLM passed.

## Follow-ups
- Only one ingested errata document. More Intel spec updates (the lineage plan) widen this.
- A symptom-based search (MSR names, instruction names) would tighten the lower bound. It needs
  a person to review every hit, so the collector records hits as `candidate` for that.
