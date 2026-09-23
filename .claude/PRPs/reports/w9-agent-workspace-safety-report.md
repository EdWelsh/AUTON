# Implementation Report: Agent Workspace Safety

## Summary

The loop could dispatch. What stopped it being used was that an architect overwrote `net.h` with
a placeholder and nothing prevented it — a single incident that has blocked **F6, V8 and H7**,
three phases across three PRDs, and has sat quoted in the PRD index long enough to become
folklore.

Reproduced first, and it was worse than the note said:

```
1. clobber:    net.h 155 bytes -> 24 bytes, silently
2. traversal:  ../escaped.txt  -> ESCAPED to the workspace's parent
3. absolute:   /tmp/probe.txt  -> WROTE outside the workspace entirely
```

The third is not a correctness bug. `write_file` is held by five agent roles, and any of them
could write anywhere the process could write.

All three now refuse, and every legitimate path still works:

```
1. clobber unread net.h            refused — read_file() first, or use edit_file()
2. traversal ../escaped            refused — resolves outside the workspace
3. absolute /tmp/probe             refused — workspace paths are relative
4. create a new file               ALLOWED
5. overwrite after reading         ALLOWED
6. edit matching once              ALLOWED
7. edit matching nothing           refused — the text is not in the file
8. edit matching twice             refused — matched 2 times and must match once
```

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Containment, checked rather than trusted | Complete | every path-taking method |
| 2 | A write that discards unseen work is refused | Complete | not a size heuristic |
| 3 | An edit primitive | Complete | `edit_file`, exactly-once |
| 4 | The incident as a regression test | Complete | 3 tests |
| 5 | Say what changed where the blocker is recorded | Complete | README + V8 row |

## Why the rule is "unread", not "too small"

The obvious guard is a size heuristic — refuse a write that shrinks a file dramatically. It would
have caught `net.h` and it will not catch the next one.

The actual defect is **writing over something you did not look at**, and that is exactly what can
be checked. `GitWorkspace` now records which paths it has read, and a whole-file write over an
existing unread file is refused. Creating a new file stays free, because a rule that makes every
write a read-first ceremony gets worked around by agents writing to new paths.

## Two `pathlib` facts that make containment non-obvious

**`Path("/ws") / "/tmp/x"` is `/tmp/x`.** An absolute path does not join — it *replaces*. So the
workspace root was silently discarded, and the check has to happen **before** joining, not after.

**A symlink inside the workspace defeats a string check.** `../` can be rejected textually; a
symlink pointing out cannot. The resolved result is what gets compared, which is what the class
already does to its own root in `__init__`.

The guard lives in `GitWorkspace`, not the tool dispatcher: `read_file`, `list_files` and
`edit_file` all take paths, and a guard on one caller leaves the others.

## Task 3: the missing primitive was the real cause

An architect replacing a header wholesale was a **legitimate intent expressed with the wrong
tool** — because whole-file replacement was the only write tool that existed. Giving agents the
right one removes the reason to reach for the wrong one.

`edit_file(path, old, new)` requires the text to match **exactly once**. Zero matches means the
agent is working from a stale assumption; more than one means it does not know which it is
changing. Applied blindly, both are silent corruption.

`write_file` was kept — an agent with no way to create a file encodes the content somewhere worse
— and its description now points at `edit_file`, since the description is the only thing steering
the choice at the moment the agent makes it.

Every role that can write can now also edit; the reviewer still has neither. A test asserts that
correspondence rather than the list, so a role added later cannot get one without the other.

## Validation

1461 unit tests pass (was 1435), 111 SLM tests. 26 new tests. Mutation-tested:

| Mutation | Tests failed |
|---|---|
| absolute paths allowed again | 1 |
| containment check removed | 5 |
| containment by string instead of resolution (symlink escape) | 5 |
| overwrite-unread allowed | 3 |
| creating a new file also requires a read (too strict) | 9 |
| edit applies on multiple matches | 3 |
| reading does not mark the file seen | 1 |
| **edit replaces every occurrence instead of one** | **0 — equivalent mutant** |

The last is genuinely equivalent, not a gap: the `count > 1` guard already guarantees a single
match, so bounded and unbounded replacement do the same thing. The bounded form is kept as the
second of two independent defences, and recorded here rather than papered over with a contrived
test.

The fifth is worth naming too — it tests the guard is not *over*-strict. A workspace that refused
to create new files would be safe and useless.

## One existing test changed

`test_tools.py::TestDeveloperTools::test_count` asserted `len(DEVELOPER_TOOLS) == 10`. It now
asserts 11 and says why it exists — every entry is capability an agent gains, so a tool arriving
unnoticed is what the count guards against.

## Files

| File | Action |
|---|---|
| `agent/orchestrator/comms/git_workspace.py` | UPDATED — `WorkspaceError`, `_resolve`, `_resolve_for_write`, `edit_file` |
| `agent/orchestrator/llm/tools.py` | UPDATED — `TOOL_EDIT_FILE`, descriptions, five role lists |
| `agent/orchestrator/agents/base_agent.py` | UPDATED — `edit_file` dispatch |
| `agent/tests/unit/comms/test_workspace_safety.py` | CREATED — 26 tests |
| `agent/tests/unit/llm/test_tools.py` | UPDATED — count and expected set |
| `.claude/PRPs/prds/README.md` | UPDATED — the blocker note |
| `.claude/PRPs/prds/auton-driver-development.prd.md` | UPDATED — V8 unblocked |

## What this does and does not unblock

It removes the reason F6, V8 and H7 were not attempted. It does **not** do them: each still needs
an actual loop run, and each is measured against a human-authored control — F4's DHCP service for
F6, V5's virtio-net for V8. Those numbers exist; the runs do not.

## Acceptance

- [x] Absolute paths, `..` traversal and symlink escapes refused by name, for every path-taking method
- [x] Creating a new file is unchanged
- [x] Overwriting a file the workspace has not read is refused, saying what to do
- [x] `edit_file` exists, requires exactly one match, offered to every role that writes
- [x] The `net.h` incident is a regression test
- [x] The blocker note says what was fixed and what still blocks F6/V8/H7
