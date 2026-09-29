# Plan: A6 — Artifact → Manifest, a second constructor and not a second pipeline

## Summary
`intent_manifest.build(sentence, …)` is today the only constructor of `Manifest`. This phase
adds `build_from_artifact(record, target=None, substrate=…) -> Manifest`, so a validated
artifact record produces **the same dataclass** a sentence does, and everything downstream
(`capability_slice`, `derive_excludes`, `gate_leakage`, `intent_service`, `package_image`) runs
unchanged. The gate has two parts: a contradictory artifact manifest is refused with its
dependency path, exactly as a sentence one is, and **zero downstream files change**, which is
checked by `git diff --stat` on the listed consumers.

## User Story
As the swarm, I want an application to enter the pipeline through the same door a sentence does,
so that the refusals, slice closure and leakage gate that already work need no second copy.

## Problem → Solution
An artifact record is not a Manifest → a constructor that maps app capabilities to the fields
the Manifest already has, with application-only facts carried in one new optional field.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `prds/auton-application-to-environment.prd.md`
- **PRD Phase**: A6
- **Estimated Files**: 4
- **Depends on**: A4 (records exist), A5 (`observed` facts exist)

---

## The mapping

| Record | Manifest field | Rule |
|---|---|---|
| `application`, subject commit | `intent` = `"application:<name>@<commit>"`, `matched` = `"artifact"` | a sentence's `matched` is a rule name; `"artifact"` is the constructor's |
| facts whose capability has a `kernel_bridge.yaml` entry | `requires` (kernel names, plus `BASE_REQUIRES`) | `capability_slice` then closes and refuses exactly as for a sentence |
| all other facts | **`application`** — new optional field, default `{}` | the one addition; see below |
| `declared`-only `listen:`, and every `unknown` | `assumptions` | the existing field for "used, not a fact" |
| `observed` / `inferred` decisions with evidence | `decisions` | same shape as driver decisions: `{capability, source, because, evidence}` |
| target (if given) | `target` | unchanged |

**The one field.** `Manifest.application: dict = field(default_factory=dict)`, emitted by
`to_json` only when non-empty. A sentence-built Manifest is byte-identical to today's; that is a
test. This lives in `intent_manifest.py` — the producer — so no consumer changes.

**Substrates.** For `substrate in ("docker", "kubernetes", "server")` the kernel `requires` is
irrelevant and `capability_slice` is not called; the manifest's content is `application`. For
`substrate == "auton"` the bridge is mandatory and an application fact with no bridge entry is
**refused**: *"`lib:libpq.so.5` has no kernel equivalent; AUTON's kernel has no POSIX by design
(intent-to-OS PRD). Choose a container or VM substrate."* That is the PRD's "refuses rather than
pretending".

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/tools/intent_manifest.py` | 73, 148-175, 201-227, 298-373 | `BASE_REQUIRES`, `Manifest`, `derive_excludes`, `build` — mirror its validate-before-derive order |
| P0 | `agent/tools/capability_slice.py` | 140-218 | the refusal with a path (`tcp -> mm`) |
| P0 | `agent/tools/intent_service.py`, `package_image.py`, `errata_join.py`, `target_spec.py` | imports of `intent_manifest` | the consumers that must not change |
| P1 | `agent/tests/unit/test_intent_manifest.py` | all | test style |

## Files to Change

| File | Action | Justification |
|---|---|---|
| `agent/tools/intent_manifest.py` | UPDATE | `application` field; `build_from_artifact`; CLI `--artifact <path> [--substrate …]` |
| `agent/tests/unit/test_manifest_from_artifact.py` | CREATE | tests below |
| `agent/tests/fixtures/artifacts/contradictory.artifact.yaml` | CREATE | needs `listen:tcp/80` (bridges to kernel `tcp`) while the target excludes `mm` |
| `agent/tests/unit/test_downstream_unchanged.py` | CREATE | the gate: sentence-built manifests are byte-identical to golden JSON captured before this change |

## NOT Building
- A second slice or leakage implementation.
- Changes to any consumer. If one proves necessary, this plan has failed its gate and the report says which file and why.

---

## Step-by-Step Tasks

### Task 1: Golden first
- **ACTION**: before editing, capture `build(s).to_json()` for all five known intents into fixtures; `test_downstream_unchanged` compares.

### Task 2: Tests (RED)
- **ACTION**: a valid artifact → Manifest with `matched == "artifact"`; unknown-to-index capability → refused (A1 validator runs first); contradictory artifact on `auton` substrate → `IntentError` whose message contains the slice path; unbridged fact on `auton` → refused with the no-POSIX message; `declared`-only port lands in `assumptions`; `docker` substrate never calls `capability_slice`.

### Task 3: Implement
- **ACTION**: `build_from_artifact` = `artifact_spec.validate` → map → (auton only) validate kernel names → `capability_slice` → `derive_excludes` → `Manifest(...)`.

### Task 4: The zero-diff check
- **ACTION**: `git diff --stat main -- agent/tools/intent_service.py agent/tools/package_image.py agent/tools/errata_join.py agent/tools/target_spec.py agent/tools/build_service.py` is empty; recorded in the report.

## Validation Commands
```bash
cd agent && ../.venv/bin/python -m pytest tests/unit/test_manifest_from_artifact.py tests/unit/test_downstream_unchanged.py tests/unit/test_intent_manifest.py -q
.venv/bin/python agent/tools/intent_manifest.py --artifact agent/tests/fixtures/artifacts/valid.artifact.yaml --substrate docker
```

## Acceptance Criteria
- [ ] Contradictory artifact refused with the dependency path.
- [ ] Sentence-built manifests byte-identical to the pre-change golden.
- [ ] Zero lines changed in the named consumers.

## Risks
| Risk | Mitigation |
|---|---|
| `package_image` iterates `to_json()` keys strictly | the field is omitted when empty; golden test catches any sentence-path change |
| The bridge is too thin to ever build on `auton` | expected; that refusal is the honest answer, and A7 turns a bridged-but-missing kernel capability into a generation task |
