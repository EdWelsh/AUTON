# Plan: A1 — Artifact Record and Validator

## Summary
The contract an Analyst writes into and every later phase reads: one record per application,
every fact carrying a `source` from a closed set (`observed` / `declared` / `inferred` /
`unknown`) and, where it names a capability, a name from a **closed application capability
index**. `artifact_spec.py --validate` refuses a fact with no source and names what is missing,
the way `target_spec.missing_facts` does for machines. This phase also settles the PRD's Open
Questions 2 and 3 — what a capability *is* for an application, and whether it lives in the
kernel's index or a second one — because every later phase depends on the answer.

## User Story
As a downstream tool (A6's `build_from_artifact`), I want an application record whose every
fact is sourced and whose every capability name is known, so that I can build a manifest from it
without re-checking what it claims.

## Problem → Solution
Nothing describes an application's needs → `agent/app_spec/capabilities.yaml` (the closed
vocabulary), an artifact record format, and a validator with a refusal per defect.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `prds/auton-application-to-environment.prd.md`
- **PRD Phase**: A1 (settles Open Questions 2, 3, and records a rule for 5)
- **Estimated Files**: 6
- **Depends on**: nothing

---

## Decisions this plan makes (and why)

| Question (PRD) | Answer here | Why |
|---|---|---|
| OQ2 — what is a capability, for an application? | A **typed** name: `kind:name`, kinds closed — `runtime`, `lib`, `path`, `device`, `listen`, `dial`, `exec`, `env`, `syscalls` | Each kind has a different ablation (A9) and a different substrate mapping (A8). An untyped name makes both guesswork |
| OQ3 — stretch the kernel index or a second one? | **A second, disjoint index**, `agent/app_spec/capabilities.yaml`, plus an explicit bridge table for the few that map to kernel capabilities (`listen:tcp` → kernel `tcp`) | `capability_slice` closes over subsystem `depends_on`. Bolting `lib:libssl.so.3` into kernel front-matter would make every kernel slice reason about userland. The bridge is the only coupling, and A7 is its only reader |
| OQ5 — is `declared` trustworthy? | Kept as one source, but `listen` facts sourced only `declared` are copied to the record's `assumptions`, mirroring `intent_manifest.DEFAULTS` → `assumptions` | `EXPOSE 8080` is a hint. Recording it as an assumption is the existing pattern for "we used this, and it is not a fact" |
| Ports | `listen:*` accepts `declared` or `observed` only; `inferred` is refused | PRD Decisions Log: "ports are never inferred" |

## Record shape (`*.artifact.yaml`)
```yaml
format: 1
application: myapp
subject: {repo: <path or url>, commit: <sha>, tree_hash: <sha256 of staged tree>}
runtime: {kind: runtime, name: python-3.12, source: declared, evidence: [{file: pyproject.toml, line: 7, quote: 'requires-python = ">=3.12"'}]}
facts:
  - {capability: "lib:libpq.so.5", source: inferred, evidence: [{file: app/db.py, line: 3, quote: "import psycopg2"}]}
  - {capability: "listen:tcp/8000", source: declared, evidence: [{file: Dockerfile, line: 22, quote: "EXPOSE 8000"}]}
  - {capability: "path:/etc/ssl/certs", source: unknown, looked_at: ["Dockerfile", "app/settings.py"]}
assumptions: []
```

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/tools/target_spec.py` | 1-60, 181-247, 366-475 | `SOURCES`, `load` refusals, `missing_facts`, `validate`, `Report` — mirror all of it |
| P0 | `agent/tools/intent_manifest.py` | 130-175, 181-200 | `DEFAULTS` → `assumptions`; DECLINED lists what is known |
| P0 | `agent/tools/capability_slice.py` | 1-140 | `SliceError` "never an empty result"; the index loader to *not* extend |
| P1 | `agent/tests/unit/test_target_spec.py` | all | test style for a validator: one test per refusal |
| P1 | `agent/tools/probe_ingest.py` | 1-20 | the "only tool that may write `probed`" rule A5 will mirror for `observed` |

## Files to Change

| File | Action | Justification |
|---|---|---|
| `agent/app_spec/capabilities.yaml` | CREATE | closed vocabulary: kinds, and for each kind the allowed name pattern; a starter set (`runtime:python-3.x`, `runtime:node-2x`, `runtime:static-elf`, common libs, `listen:tcp/*`, …) |
| `agent/app_spec/kernel_bridge.yaml` | CREATE | app capability → kernel capability, for A7 only |
| `agent/tools/artifact_spec.py` | CREATE | `load`, `missing_facts`, `validate`, `known_capabilities`, CLI `--validate` / `--known` |
| `agent/tests/unit/test_artifact_spec.py` | CREATE | one test per refusal |
| `agent/tests/fixtures/artifacts/*.artifact.yaml` | CREATE | one valid, one per defect |
| `docs/ARCHITECTURE.md` | UPDATE | one paragraph: the second index and why it is disjoint |

## NOT Building
- The Analyst (A3) or anything that writes records.
- Version resolution. `runtime:python-3.12` is a name, not a solver input.
- A writer of `observed`. The validator *accepts* `observed`; A5 enforces who may write it.

---

## Step-by-Step Tasks

### Task 1: Refusal tests first (RED)
- **ACTION**: tests that `validate` refuses, each with a message naming the field and what would fix it: no `source`; `source` not in the four; a capability absent from the index (**message lists known names of that kind**); `inferred` on `listen:*`; `declared`/`inferred` with no `evidence`; evidence missing `file`, `line` or `quote`; `unknown` with no `looked_at`; `subject.tree_hash` absent. And that a valid record passes and `declared`-only `listen` facts appear in `assumptions`.

### Task 2: The index
- **ACTION**: `capabilities.yaml` with kinds and patterns; loader returns a frozen mapping; unknown kind refused.
- **GOTCHA**: patterns must be anchored (`listen:tcp/[0-9]{1,5}`), or the "closed" vocabulary is open by regex.

### Task 3: `artifact_spec.py`
- **ACTION**: mirror `target_spec`'s `load` → `missing_facts` → `validate` → `Report.ok`; CLI exit 0 valid, 1 refused, 2 unreadable.

### Task 4: The bridge
- **ACTION**: `kernel_bridge.yaml`; a test that every right-hand side is a real kernel capability via `capability_slice.load_specs()` + `capability_owner()` — a bridge naming a phantom kernel capability fails the suite.

## Validation Commands
```bash
cd agent && ../.venv/bin/python -m pytest tests/unit/test_artifact_spec.py -q
.venv/bin/python agent/tools/artifact_spec.py --validate agent/tests/fixtures/artifacts/valid.artifact.yaml
.venv/bin/python agent/tools/artifact_spec.py --known listen
```

## Acceptance Criteria
- [ ] Every refusal in Task 1 is tested and names what to fix.
- [ ] An unknown capability's refusal lists the known names of its kind.
- [ ] Every bridge entry resolves in the kernel index, by test.
- [ ] No existing file under `agent/kernel_spec/` changes.

## Risks
| Risk | Mitigation |
|---|---|
| The starter vocabulary is too small and A4 refuses everything | expected and correct: growing the index is a reviewed edit to one YAML file, which is the point of a closed vocabulary |
| Kinds prove wrong once A5 observes real apps | `format: 1` field; a kind change is a format bump with a migration test |
