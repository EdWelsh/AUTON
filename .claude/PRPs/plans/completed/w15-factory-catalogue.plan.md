# Plan: Catalogue + roles.c Truth-Up (F12)

## Summary
`roles.c` is a hand-maintained table of 7 services, 2 `CAP_WORKING` and 5 `CAP_ROADMAP` with
blockers typed as prose (base `kernel/slm/roles.c:22-41`). After F4–F11 some rows become "a
dedicated AUTON image does this", which the table cannot express, and the prose will go stale
the moment a service lands. This plan makes the catalogue **data derived from the specs and the
build results**, generates the role table from it, and makes chat answer `what can you do` and
`be an email server` with the three-way truth the PRD asks for.

## User Story
As a chat user, I want "be a database" to tell me whether this image does it, which AUTON image
does, and how to build it, so that the OS never promises what it cannot do.

## Problem → Solution
A hand-written C table with prose blockers → `agent/kernel_spec/catalogue.yaml`, generated from
`services/*.md` + the recorded build results; `agent/tools/gen_roles.py` emits `roles_table.c`;
three statuses: `in-image`, `dedicated-image` (with the build command), `roadmap` (with the
blocker linked to its decision or plan).

## Metadata
- **Complexity**: Medium
- **Source PRD**: `auton-service-kernel-factory.prd.md` phase 12
- **Estimated Files**: 6
- **Depends on**: F8, F9 landed (per the PRD); F10/F11 outcomes read if present

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | base `kernel/slm/roles.c` | 1-120 | `cap_status_t`, the table, how chat prints ` - ready` / ` - roadmap` (`:87`), `action` dispatch (`:110`) |
| P0 | `agent/tools/gen_absent.py` | 1-60 | the precedent for generating C into `build-<svc>/generated/` rather than `kernel/` (see `build_service.py` comment about the poisoned glob) |
| P0 | `agent/tools/build_service.py` | 300-340 | where generated sources join the link |
| P1 | `agent/tools/intent_manifest.py` | INTENTS | phrase → intent; the catalogue should agree with it (one vocabulary) |
| P1 | `agent/kernel_spec/services/*.md` | front-matter | the source rows |

## Patterns to Mirror
### GENERATED_C_LOCATION
// SOURCE: agent/tools/build_service.py:305-312
```python
# Generated into build/, not kernel/. The Makefile globs `kernel` for
# sources, so a generated file left under it is compiled into every
# subsequent build ...
absent = tree / f"build-{name}" / "generated" / "absent.c"
```
### STATUS_ENUM
// SOURCE: base kernel/slm/roles.c:10 `typedef enum { CAP_WORKING, CAP_ROADMAP } cap_status_t;`

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/kernel_spec/catalogue.yaml` | CREATE | one row per role phrase set: `service`, `status`, `blocker` (a path to a decision/plan/report), `build` command |
| `agent/tools/gen_roles.py` | CREATE | `catalogue.yaml` + which services this image contains → `roles_table.c` (`CAP_IN_IMAGE`, `CAP_DEDICATED`, `CAP_ROADMAP`) |
| `agent/tools/build_service.py` | UPDATE | emit `roles_table.c` beside `absent.c`, so every image knows its own row and its siblings' |
| `agent/kernel_spec/subsystems/slm.md` | UPDATE | the roles contract: three statuses and the exact chat phrasing |
| `agent/tests/unit/test_catalogue.py` | CREATE | every `services/*.md` has a row; every `dedicated-image` row has a report proving the image built; no row says `in-image` for a service not in the slice |
| `agent/tests/unit/test_gen_roles.py` | CREATE | the generated C compiles (host clang `-fsyntax-only`) and the dispatch only names symbols the slice defines |

## NOT Building
- Hand edits to `roles.c` in any tree. It becomes generated input.
- Building images on demand from chat (the control plane's job).

## Step-by-Step Tasks
### Task 1: `catalogue.yaml` from the facts
- **ACTION**: Rows for web, dns, file, database, ssh, email, dhcp, tftp, doom, and the control-plane rows (desktop/docker/k8s). Every `status` cites evidence: a report path for `dedicated-image`, a decision or plan path for `roadmap`.
- **GOTCHA**: SSH's row depends on the F10 gate: CUT → `roadmap` citing `decisions/ssh-crypto.md`, never "coming soon".

### Task 2: Test the catalogue against the repo (RED → GREEN)
- **IMPLEMENT**: `test_catalogue.py` as above. It fails if a spec has no row, or a row cites a missing file.

### Task 3: `gen_roles.py`
- **IMPLEMENT**: emit the table with `action` set only for `CAP_IN_IMAGE` rows whose entry symbol is in the image's slice. For `CAP_DEDICATED` the note is `"a dedicated AUTON image does this: <build>"`.
- **GOTCHA**: The current table points `action` at `http_server_run` directly. A dedicated-image row must have `action = 0`, or the absence stub from `gen_absent.py` gets called and prints `[ABSENT]` as if it were the service.

### Task 4: Wire into the build
- **ACTION**: `build_service.py` writes `build-<svc>/generated/roles_table.c` and excludes the tree's own `roles.c` table. Keep `roles.c` code, replace the data.
- **VALIDATE**: `build_service.py dhcp --tree <ws>` links; the serial shows `be a database` → the dedicated-image answer.

### Task 5: Spec the chat phrasing
- **ACTION**: `slm.md` roles section with the three exact answer templates. The acceptance markers assert them.

## Validation Commands
```bash
cd agent && ../.venv/bin/python -m pytest tests/unit/test_catalogue.py tests/unit/test_gen_roles.py -q
.venv/bin/python agent/tools/build_service.py fileserver --tree <ws> --iso   # then ask "be a database"
```

## Acceptance Criteria
- [ ] Every registry row is verifiable from a file in the repo
- [ ] "be an email server" gives a useful answer in every image (in-image, dedicated, or a cited roadmap)
- [ ] `roles.c` data is generated, never hand-edited

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Catalogue drifts from `intent_manifest.INTENTS` | M | M | a test asserts the phrase vocabularies agree |
| A generated table calls a stub as if it were a service | M | H | Task 3's gotcha, pinned by `test_gen_roles` |


---

## Progress: Tasks 1-3 (2026-09-22)

`catalogue.yaml` (14 roles, four statuses, citations checked to be git-TRACKED files), `gen_roles.py`, and `test_catalogue.py`. **Remaining**: Task 4 (wire into `build_service.py`, which needs roles.h's new enum in a tree) and Task 5 (the chat phrasing in `slm.md`).


---

## Closed 2026-09-23

COMPLETE. catalogue.yaml, gen_roles.py, the build wiring and slm.md's role-table phrasing all landed, with 18 tests.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
