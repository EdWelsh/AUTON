# Plan: Unmitigated Sweep: Published Errata No OS Mitigates (H12)

## Summary
The PRD asks for *"published errata that no OS mitigates on the test fleet. Report with a
count."* There is no fleet (`CONFORMANCE-HARDWARE.md`), but the desk half is answerable now:
join every ingested erratum against (a) the vendor's own status/workaround fields and (b) whether
any mainstream OS documents a mitigation for it. The count of errata marked **No Fix** with **no
workaround** and **no documented OS mitigation** is the deliverable. It is a number the security
community rarely states, with every row cited. The on-fleet half (does a real machine exhibit
it) waits on H10 venues and is scoped out explicitly.

## User Story
As a reader of AUTON's security claims, I want the count of documented silicon defects nobody
mitigates, each cited, so that "is this machine safe?" can distinguish "fixed", "worked around"
and "known and unaddressed everywhere".

## Problem → Solution
Errata status exists per record; no cross-OS mitigation data exists → `os-mitigations.yaml`
(hand-curated: erratum → Linux/Windows/BSD mitigation evidence with URLs, reading documentation
only, never copying code), `sweep.py` producing the count and the list, refreshed as documents
are added (H9).

## Metadata
- **Complexity**: Medium (curation-heavy)
- **Source PRD**: `auton-hardware-truth.prd.md`
- **PRD Phase**: H12 (desk half)
- **Estimated Files**: 5
- **Depends on**: H4, H6 (landed); benefits from `w13-hardware-errata-lineage` (more documents)

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/tools/vendor_ingest.py` | 39-66 | `status`, `workaround` fields |
| P0 | `agent/tools/mitigation_registry.py` | 128-160 | `assess()` categories: applicable/mitigable/declined/unmitigatable |
| P0 | `.claude/PRPs/prds/auton-hardware-truth.prd.md` | Open Questions 2, 6 | Linux `bugs.c` licensing; "do not use this silicon" as a mitigation |
| P1 | `agent/kernel_spec/mitigations/README.md` | 24-34 | field rules the sweep's vocabulary must match |

## Patterns to Mirror
### CITED_OR_ABSENT
// SOURCE: agent/tools/vendor_ingest.py:57-66: every fact cites its source. A mitigation claim in `os-mitigations.yaml` without a URL is refused by the loader.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/hardware/os-mitigations.yaml` | CREATE | `erratum → [{os, evidence_url, kind: kernel-workaround / microcode / documentation-only / none-found, checked: date}]` |
| `agent/tools/sweep.py` | CREATE | ingested errata × vendor status × OS evidence → counts per bucket + the unmitigated list with citations |
| `agent/tests/unit/test_sweep.py` | CREATE | bucket logic; a claim without a URL refused; `none-found` distinct from "not checked" |
| `.claude/PRPs/reports/w13-hardware-unmitigated-sweep-report.md` | CREATE | the count, method, and what "none found" does and does not mean |

## NOT Building
- Fleet verification (needs H10 on metal).
- Copying Linux `bugs.c`. Its public documentation (`Documentation/admin-guide/hw-vuln/`) and
  commit messages are read as evidence of *whether* something is mitigated.

## Step-by-Step Tasks
### Task 1: The vocabulary
- **ACTION**: buckets: `vendor-fixed` (a stepping or microcode fix), `vendor-workaround`, `os-mitigated`, `documented-unmitigated` (No Fix, no workaround, `none-found` in every OS checked), `not-checked`.
- **GOTCHA**: "not checked" and "checked, none found" must never merge. The count is only of the second.

### Task 2: Curate, starting with 682436 (94 errata)
- **ACTION**: For each No Fix erratum, search Linux `hw-vuln` docs and the git log messages, Windows KB, and FreeBSD errata notices. Record the URL or `none-found` with the date.
- **VALIDATE**: 100% of No Fix errata in 682436 carry a bucket.

### Task 3: The sweep tool + tests

### Task 4: Report the count
- **ACTION**: "N of 94 errata in Intel 682436 are documented, unfixed, without a workaround, and unmitigated in the OSes checked (list, each cited)". Zero is reported as a finding too.

## Validation Commands
```bash
.venv/bin/python agent/tools/sweep.py --document intel/intel-spec-update
cd agent && ../.venv/bin/python -m pytest tests/unit/test_sweep.py -q
```

## Acceptance Criteria
- [ ] Every No Fix erratum in each ingested document bucketed with evidence
- [ ] The count published with its method and limits
- [ ] "not checked" never counted as "unmitigated"

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Absence of evidence read as evidence of absence | H | M | the bucket name and the report say "none found in <sources>, <date>" |
| Linux licence contamination | L | M | documentation and commit messages only; stated in the file header |
