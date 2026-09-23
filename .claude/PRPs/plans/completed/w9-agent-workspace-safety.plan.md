# Plan: Agent Workspace Safety

**Source**: not a PRD phase — the blocker recorded in `.claude/PRPs/prds/README.md:192`
**Blocks**: **F6** (agent-authored service), **V8** (agent-authored driver), **H7** (generated
mitigations) — three phases across three PRDs
**Precedent for planning it anyway**: wave 0 did the same. The scheduler fix *"appears in no PRD's
phase table"* and was the first thing planned, because everything downstream cost less after it.

## Summary

The loop can dispatch. What stops it being used is that an architect overwrote `net.h` with a
placeholder and nothing prevented it.

Reproduced, and it is worse than the record says:

```
1. clobber:    net.h 155 bytes -> 24 bytes, silently
2. traversal:  ../escaped.txt  -> ESCAPED to the workspace's parent
3. absolute:   /tmp/probe.txt  -> WROTE outside the workspace entirely
```

The third is not a correctness bug. `write_file` is held by five agent roles, and an agent holding
it can write anywhere the process can write.

## Evidence

- `agent/orchestrator/comms/git_workspace.py:104-108` — `write_file` in full:
  `full_path = self.path / path`, `mkdir(parents=True)`, `write_text`. No containment check, no
  existence check, no comparison with what was there.
- `pathlib` semantics make this worse than it reads: `Path("/ws") / "/tmp/x"` is `/tmp/x`. An
  absolute path does not join, it *replaces*, so the workspace root is silently discarded.
- `agent/orchestrator/llm/tools.py:26-46` — `TOOL_WRITE_FILE`, *"The full content to write"*.
  Whole-file replacement is the only write primitive that exists; there is no edit.
- `agent/orchestrator/llm/tools.py:462-517` — held by `ARCHITECT_TOOLS`, `DEVELOPER_TOOLS`,
  `TESTER_TOOLS`, `INTEGRATOR_TOOLS` and `DATA_SCIENTIST_TOOLS`. Five roles, one unguarded write.
- `.claude/PRPs/prds/README.md:192` — *"The loop can dispatch, but an architect overwrote `net.h`
  with a placeholder. Workspace isolation and write granularity come first."*
- `agent/tools/disclosure.py`, `agent/tools/vendor_inventory.py` `is_tracked_path` — the house
  precedent: a tool that writes refuses a destination it must not touch, and the refusal is
  tested rather than documented.
- `.claude/PRPs/reports/w0-agent-shell-hardening.md` — H0's reasoning applies unchanged: agents
  are about to generate far more code, and fixing the write path afterwards means auditing
  whatever they wrote in the meantime.

## Patterns to Mirror

- **Refuse with the path in the message**: `capability_slice.capability_slice`, `disclosure.py`.
- **argv, not a string**: H0's shape — remove the dangerous primitive rather than sanitising its
  input.
- **Three states**: a write that is new, a write that matches what the agent read, and a write
  that would discard something it never saw.
- **Test the refusal, do not document it**: `vendor_inventory.fetch_plan` refusing a tracked
  destination.

## Tasks

### Task 1: Containment, checked rather than trusted
- **Action**: Every path is resolved and must land inside the workspace root. Absolute paths and
  `..` traversal are refused by name.
- **Why resolve rather than reject `..` textually**: a symlink inside the workspace pointing out
  of it defeats a string check, and `Path.resolve()` is what the class already does to its own
  root at `__init__`.
- **Gotcha**: `Path(root) / "/tmp/x"` == `/tmp/x`. The join silently discards the root, so an
  absolute path must be caught **before** joining, not after.
- **Gotcha**: the check belongs in `GitWorkspace`, not in the tool dispatcher. `read_file`,
  `list_files` and `search_code` take paths too, and a guard on one caller leaves the others.
- **Validate**: `../x`, `/tmp/x` and a symlink escape are each refused naming the path; a normal
  relative path still writes.

### Task 2: A write that discards unseen work is refused
- **Action**: Overwriting an existing file requires the agent to have read it in this session.
  `GitWorkspace` tracks what was read; a write to a file it has not seen is refused with what to
  do instead.
- **Why this rule and not a size heuristic**: "the new content is much shorter" would have caught
  `net.h` and will not catch the next one. The defect is writing over something you did not look
  at, and that is exactly what can be checked.
- **Gotcha**: creating a new file must stay free. A rule that makes every write a read-first
  ceremony will be worked around by agents writing to new paths.
- **Gotcha**: the read-set is per-workspace-instance, not per-agent. Two agents sharing a
  workspace is the collaboration model; a read by one is not consent from the other. State whether
  that is acceptable or key the set by agent.
- **Validate**: writing a new file succeeds; overwriting an unread file is refused; reading then
  overwriting succeeds.

### Task 3: An edit primitive, so agents stop replacing whole files
- **Action**: `edit_file(path, old, new)` on the workspace and a matching tool, replacing an exact
  substring that must appear exactly once.
- **Why exactly once**: an edit matching twice is ambiguous and an edit matching zero times is a
  stale assumption. Both are silent corruption when applied blindly.
- **Why this fixes the incident properly**: an architect replacing a header wholesale is a
  *legitimate intent expressed with the wrong primitive*. Giving it the right one removes the
  reason to reach for the wrong one.
- **Gotcha**: do not remove `write_file`. New files need it, and an agent with no way to create a
  file will encode content some worse way.
- **Validate**: an edit matching once applies; zero and multiple matches are refused naming the
  count.

### Task 4: The incident, as a regression test
- **Action**: A test that reproduces the recorded failure — a substantial header replaced by a
  placeholder — and asserts it is now refused.
- **Why**: this is the defect that stopped three phases across three PRDs. A defect with no test
  is an intention, and this one has been quoted in the PRD index for long enough to become
  folklore.
- **Validate**: the test fails if any of Tasks 1–3 is reverted.

### Task 5: Say what changed where the blocker is recorded
- **Action**: Update `.claude/PRPs/prds/README.md:192` and the three phase rows that cite F6.
- **Gotcha**: do not mark F6, V8 or H7 complete. This unblocks them; it does not do them.
- **Validate**: the README says what was fixed and what remains.

## Validation

```bash
cd agent && python -m pytest tests/unit/test_git_workspace.py -q
cd agent && python -m pytest tests/unit -q
python - <<'PY'   # the three probes from the summary, all now refused
from orchestrator.comms.git_workspace import GitWorkspace
PY
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| The read-before-write rule makes the loop unusable | **H** | Task 2's first gotcha: new files stay free, and the refusal says to read first rather than failing opaquely |
| Containment breaks existing callers that pass absolute paths | **M** | Task 1 checks before joining; the tests name every caller that takes a path |
| A symlink inside the workspace defeats the check | **M** | Task 1 resolves rather than matching text |
| Two agents share a workspace and one's read authorises the other's write | **M** | Task 2's second gotcha — decided explicitly, not by default |
| `write_file` is removed and agents encode content elsewhere | **M** | Task 3 keeps it for new files |

## Acceptance
- [ ] Absolute paths, `..` traversal and symlink escapes are refused by name, for every path-taking method
- [ ] Creating a new file is unchanged
- [ ] Overwriting a file the workspace has not read is refused, saying what to do
- [ ] `edit_file` exists, requires exactly one match, and is offered to the roles that write
- [ ] The `net.h` incident is a regression test
- [ ] The blocker note in `prds/README.md` says what was fixed and what still blocks F6/V8/H7
