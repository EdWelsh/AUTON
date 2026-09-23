# Implementation Report: Agent-Authored Driver (V8)

## Summary

**Same result as F6, for the same reasons.** One pre-registered run on gemma4 lasted **89
seconds and two iterations** and wrote **nothing**. There is no spec section, no record and no
test. Two "read the spec" tasks were each sent to review with an empty diff, and both were
rejected over *"`struct page` handling"* in code that does not exist. The rest of the chain
blocked.

That makes the F6 failure reproducible across a different goal, workspace, subject and
subsystem. It is the loop, not the run. See the F6 report for the three engine lines.

The phase's security question, *"can an agent write a driver anyone should run?"*, was not
reached. Its preconditions were, and one of them turned up something about V5 and V6.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Choose the device, run the selector first | Complete | `virtio-console` (`virtio-mmio:3`, `1af4:1043`), no existing record. Selector result recorded verbatim **before** the run |
| 2 | Reuse F6's harness | Complete | `measure_authorship.py --driver …` reproduces V5/V6 in part; differences below |
| 3 | Run the loop once | Complete | 17:33:12Z–17:34:41Z. Artifacts in `.artifacts/authorship/2026-09-21-v8/` |
| 4 | Injected-bug testing | **Not applicable** | no tests or reference were produced to inject into |
| 5 | `status: specified` at most | Trivially held | no record exists. No exception was argued for |

## Task 1: the selector, and what it said about V5 and V6

Before anything was fetched, the selector **refused**:

```
synthesize  blocked  Virtual I/O Device (VIRTIO) Specification is inventoried but not ingested
                     — run vendor_fetch.py oasis-virtio/virtio-spec
```

After ingesting VIRTIO 1.2 cs01 from docs.oasis-open.org (1,213,207 bytes, sha256
`42c7d2b9da95b476…`, cached under the gitignored `.cache/vendor/`; not redistributable, and not
committed):

```
-> synthesize  available  Virtual I/O Device (VIRTIO) Specification is inventoried and ingested
                          basis: oasis-virtio/virtio-spec
```

**V5 and V6 both recorded `strategy: synthesize` citing VIRTIO 1.2 while the specification was
not ingested on this machine.** By V4's own rule, the selector would have refused them. The
records are not wrong about the document. They were written without the check that exists to
stop exactly that. After this ingestion, their basis now resolves.

## What happened in the run

```
Planning  7 tasks: spec-001 "Read Architecture Specification", spec-002 "Read Drivers
          Specification", spec-003 update drivers.md, spec-004 record, test-001..003
Iter 0    spec-001 → architect → success on `main` → review of an empty diff →
          "the struct page handling is incorrect" → BLOCKED
Iter 1    spec-002 → same → "struct page handling needs careful review" → BLOCKED
Iter 2    nothing ready → exit. Every agent branch: empty diff against main
```

## Task 2: the controls, re-counted

| | V5 recorded | V5 measured | V6 recorded | V6 measured |
|---|---|---|---|---|
| Spec lines | 113 | **113** ✓ | 84 | **85** (the section's growth over HEAD; ±1 is a boundary line) |
| Test lines | 160 | **160** ✓ | 136 | **136** ✓ |
| Test cases | 29 | **28** | 16 | **16** ✓ |
| Reference, new | 135 | not reproducible | 24 | not reproducible |
| Reference today | | 167 (V5 + V6 together) | | 167 reused |

- **V5's 29 cases is 28.** `grep -c 'ok('` gives exactly 29 because it counts the helper's own
  definition. V6's 16 and F4's 24 excluded it, so V5 almost certainly did not. Twenty-eight
  checks also print `PASS` at runtime.
- **The reference split can't be recovered.** `tests/kernel/virtio_reference/`,
  `virtio_net_test.c` and `virtio_blk_test.c` are **untracked**: V5, V6 and V7 were never
  committed. V6 extended V5's reference in place, and no history records either version. The
  "0.18 new-reference ratio" that V6 called the finding that mattered is not reproducible from
  any artifact.

That is the strongest argument in this session for committing the w6–w10 work before it goes
further.

## For the next PRD session

1. The loop defects in the F6 report come first. V8 cannot be re-run meaningfully before them.
2. **Commit V5–V7's host references and tests.** A control that lives only in a working tree is
   a control that cannot be re-measured, as this report just found.
3. When V8 is re-run, Task 4 (injected bugs) is the part that matters. The gates only prove a
   driver's own checks pass, and V5 showed two of those passed for the wrong reason until the
   tests were improved.
