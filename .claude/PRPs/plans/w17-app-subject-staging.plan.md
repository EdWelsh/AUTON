# Plan: A2 — Subject Staging, read-only inside the workspace

## Summary
The Analyst has to read a repository that is not the kernel workspace. The PRD rejects a new
`read_subject_file` tool because it would be a second traversal surface. Instead the subject
is **staged** into the workspace at `.auton/subject/`, where `read_file`, `search_code` and
`list_files` already reach it through the sandbox that `test_workspace_safety.py` proves, and one
rule is added: **nothing may write under `.auton/subject/`.** This plan found that the rule
needs three layers, not one, because agents hold a `shell` tool whose allowlist includes
`python` and `git`: a tool-level refusal, filesystem read-only bits, and a tree hash checked
before any Analyst output is accepted.

## User Story
As the Analyst, I want to read the subject application with the tools I already have, and as the
owner I want proof that nothing the analysis did changed the evidence it analysed.

## Problem → Solution
No way to reach the subject; any write path would be an injection surface →
`GitWorkspace.stage_subject(src)` copies (never symlinks) a clean export into
`.auton/subject/`, records its sha256 tree hash, removes write bits; `_resolve_for_write` and
`edit_file` refuse the prefix; `verify_subject()` recomputes the hash and refuses on mismatch.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `prds/auton-application-to-environment.prd.md`
- **PRD Phase**: A2
- **Estimated Files**: 5
- **Depends on**: nothing (A1's record stores the hash this produces)

---

## Why three layers
| Write path | Stopped by |
|---|---|
| `write_file` / `edit_file` into `.auton/subject/…` | layer 1: `_resolve_for_write` / `edit_file` refuse the prefix, with a message saying the subject is evidence |
| `shell python -c "open('.auton/subject/x','w')"` (allowlisted: `agent/orchestrator/llm/tools.py:238-241`) | layer 2: files `0444`, dirs `0555` — a plain open-for-write fails |
| `shell python -c "os.chmod(...)"`, then write; `shell git checkout` over it | layer 3: `verify_subject()` tree hash — any change, by any path, is detected before the Analyst's record is accepted |

Layer 3 is the gate; 1 and 2 make the honest failure early and legible. `.auton` is already
excluded from agent commits (`git_workspace.py:307`, `_NOT_WORK`), so the subject is never
committed onto an agent branch.

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/orchestrator/comms/git_workspace.py` | 41-106, 200-290, 303-307 | `WorkspaceError`, `_resolve`, `_resolve_for_write`, `edit_file`, `search_code`, `_NOT_WORK` |
| P0 | `agent/tests/unit/comms/test_workspace_safety.py` | all | the three reproduced escapes and how they are tested; mirror the style |
| P1 | `agent/orchestrator/agents/base_agent.py` | 177-245, 405-430 | every file tool goes through `self.workspace`; `_run_allowlisted` |
| P1 | `agent/orchestrator/llm/tools.py` | 238-260 | `SHELL_ALLOWLIST` |

## Files to Change

| File | Action | Justification |
|---|---|---|
| `agent/orchestrator/comms/git_workspace.py` | UPDATE | `SUBJECT_DIR = ".auton/subject"`, `stage_subject(src) -> str` (hash), `verify_subject(expected)`, prefix refusal in `_resolve_for_write` and `edit_file` |
| `agent/orchestrator/comms/subject_hash.py` | CREATE | deterministic tree hash: sorted relative paths, mode, sha256 of content; symlinks recorded as their target string and **never followed** |
| `agent/tests/unit/comms/test_subject_staging.py` | CREATE | tests below |
| `agent/orchestrator/llm/tools.py` | UPDATE | `read_file`/`search_code` descriptions mention `.auton/subject/` |
| `docs/ARCHITECTURE.md` | UPDATE | the rule, and the three layers |

## NOT Building
- A new read tool (PRD Decisions Log).
- Fetching a remote subject. `stage_subject` takes a local path; cloning is the caller's job, and a URL is D-A3's question.
- Sandboxing the shell tool generally. Layer 3 detects; it does not prevent, and says so.

---

## Step-by-Step Tasks

### Task 1: Tests first (RED)
- **ACTION**: `test_subject_staging.py`:
  - staged files are readable via `read_file`, found by `search_code`, listed by `list_files`;
  - `write_file`/`edit_file` under `.auton/subject/` raise `WorkspaceError` naming the rule — **including** `.auton/subject/../subject/x` and a case-variant on a case-insensitive FS;
  - a plain `open(..., "w")` on a staged file raises `PermissionError`;
  - after `chmod` + write via Python (simulating the shell path), `verify_subject` raises and names the changed path;
  - a symlink in the subject pointing outside is staged as a link, not followed, and `read_file` through it is refused by `_resolve`;
  - the hash is stable across two stagings of the same tree and changes when one byte does;
  - `commit()` on an agent branch never includes `.auton/subject`.

### Task 2: Hash
- **ACTION**: `subject_hash.tree_hash(root)`; exclude nothing — `.git` is not staged at all (export, don't copy).

### Task 3: Stage
- **ACTION**: `stage_subject(src)`: refuse if `SUBJECT_DIR` exists (restaging is a new run); `git -C src archive HEAD | tar -x` when `src` is a repo (records the commit), else `shutil.copytree(symlinks=True)`; set modes; return hash.

### Task 4: Refuse writes
- **ACTION**: in `_resolve_for_write` and `edit_file`, compare the **resolved** path against `(self.path / SUBJECT_DIR).resolve()`; refuse with *"refusing to write {path!r}: .auton/subject/ is the application under analysis, and evidence the analysis can edit is not evidence"*.

### Task 5: Scored by attempting one
- **ACTION**: the PRD gate is "scored by attempting one". Add a scripted-agent test that issues each write path from the table and asserts each is stopped by the layer named.

## Validation Commands
```bash
cd agent && ../.venv/bin/python -m pytest tests/unit/comms -q
```

## Acceptance Criteria
- [ ] All three read tools reach the subject unchanged.
- [ ] Every write path in the table is stopped by the named layer, by test.
- [ ] `test_workspace_safety.py` passes unchanged.

## Risks
| Risk | Mitigation |
|---|---|
| Read-only bits break workspace teardown (`rm -rf` of a `0555` tree fails) | add `unstage_subject()` (GitWorkspace has no teardown today) that restores write bits on the subject only, then removes it; experiment scripts call it |
| Large subjects blow up `search_code` output | it already truncates to 50 results (`base_agent.py:208`) |
| Windows ignores POSIX modes | layer 2 is best-effort there; layer 3 still holds, and the test marks layer 2 POSIX-only |
