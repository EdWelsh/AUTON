# Plan: Agent Shell Hardening (H0)

**Source PRD**: `.claude/PRPs/prds/auton-hardware-truth.prd.md` — phase H0
**Complexity**: Small for the internal callers; **a design decision** for the `shell` tool
**Blocks**: all vendor-document ingestion (H2, H3), and should precede any increase in
generated code volume

## Summary

`base_agent.py:320` runs `asyncio.create_subprocess_shell(command)` on a string. Three callers
build that string, and they are not the same problem:

- `:216` passes `tool_input["command"]` straight through — a **model-controlled string
  reaching a shell**. This is a `shell` tool, so it is arguably working as designed; the
  question is whether agents should have arbitrary shell at all.
- `:311` builds `" ".join(["make", "-C", str(path), target])`.
- `:315` builds an f-string interpolating `self.workspace.path` and `test_name`.

The latter two have no reason to involve a shell. The first needs a decision before
hardware-truth points agents at externally fetched vendor documents while they hold one.

## Evidence

- `base_agent.py:320` — `create_subprocess_shell`, taking `command: str`.
- `base_agent.py:216` — `self._run_shell(tool_input["command"], ...)`. `tool_input` is model
  output.
- `base_agent.py:311` — `" ".join(cmd)` where `cmd` contains a filesystem path.
- `base_agent.py:315` — `f"make -C {self.workspace.path} test-{test_name}"`.
- Recorded as out of scope and deferred to "the security PRD" in
  `.claude/PRPs/reports/e2e-orchestrator-lane.md:111`.
- Phase 8 ran the loop only against a local model on a hand-written goal *because* of this.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Argv subprocess | `agent/tools/kernel_graph.py:clang_ast` | `subprocess.run([...], capture_output=True, timeout=…)` — a list, never a string |
| Timeout + capture | `base_agent.py:329-331` | `asyncio.wait_for(proc.communicate(), timeout=…)`; keep this |
| Output shape | `base_agent.py:333-339` | stdout, then `[stderr]`, then `[exit code: N]` — agents parse this; do not change it |
| Honest refusal | `kernel/slm/roles.c` `CAP_ROADMAP` | Say what is not permitted and why, rather than failing opaquely |

## Files to Change

| File | Action | Why |
|---|---|---|
| `agent/orchestrator/agents/base_agent.py` | UPDATE | `_run_argv` alongside `_run_shell`; internal callers move over |
| `agent/orchestrator/llm/tools.py` | UPDATE | The `shell` tool's schema and description, per the Task 2 decision |
| `agent/tests/unit/orchestrator/test_base_agent.py` | CREATE/UPDATE | Injection attempts are rejected; argv path preserves output shape |

## Tasks

### Task 1: Argv for every internal caller
- **Action**: Add `_run_argv(self, argv: list[str], timeout: int)` using
  `asyncio.create_subprocess_exec`. Move `:311` and `:315` to it. Neither needs shell
  features — no pipes, no globs, no redirection.
- **Mirror**: `kernel_graph.py`'s `subprocess.run([...])`; keep the output format from
  `base_agent.py:333-339` byte-identical, because agents parse it.
- **Validate**: a workspace path containing a space or a `;` runs correctly instead of
  fragmenting.

### Task 2: Decide what the `shell` tool is
- **Action**: A decision with three defensible answers, to be **recorded** rather than
  defaulted:
  1. **Remove it.** Agents get `read_file`, `write_file`, `list_files`, `search_code`,
     `build`, `test` — the measured 8/8 tool-calling used only those. Nothing observed
     required arbitrary shell.
  2. **Allowlist it.** A fixed set of argv heads (`make`, `git`, `clang`) with arguments
     passed as a vector, never a string.
  3. **Sandbox it.** Keep shell semantics inside a container or a restricted user.
- **Recommendation**: (1), then (2) if a real need appears. The tool-calling measurement is
  evidence that no agent reached for shell when given specific tools.
- **Validate**: whichever is chosen, `grep -rn "create_subprocess_shell" agent/` returns only
  a deliberately sandboxed path, or nothing.

### Task 3: Prove injection is closed
- **Action**: Tests that attempt injection through every remaining path — a `test_name` of
  `x; touch /tmp/pwned`, a workspace path containing `$(...)`, a make target with a newline.
  Assert the side effect does **not** occur and the call either runs literally or is refused
  with a reason.
- **Why**: this is a security fix, so the test is the deliverable. A fix with no adversarial
  test is an assertion.
- **Validate**: each attempt leaves no artefact; the suite fails on `HEAD~`.

### Task 4: Re-run the lane
- **Action**: `scripts/orchestrate-native.sh` against a small goal, confirming the loop still
  builds and tests through the new path.
- **Validate**: the run reaches a terminal phase; build and test tool output is unchanged in
  shape.

## Validation

```bash
grep -rn "create_subprocess_shell" agent/          # expect none, or one sandboxed site
cd agent && python -m pytest tests/unit/orchestrator/test_base_agent.py -q
scripts/orchestrate-native.sh "read kernel/net/arp.c and report what arp_input does"
test ! -e /tmp/pwned                               # injection tests leave nothing behind
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Removing `shell` breaks an agent that depended on it | **M** | Measured: 8/8 tool calls used specific tools, none used shell. Reinstate as an allowlist if a real need appears |
| Output-format change breaks agent parsing | **M** | Keep `base_agent.py:333-339` byte-identical; it is a contract |
| Hardening gives false confidence | **M** | The threat is untrusted *input* (vendor documents), not just the shell. Ingestion must still treat fetched documents as hostile |
| A sandbox is chosen and becomes the only tested path | **L** | Whichever option is chosen, Task 3's adversarial tests run against it |

## Acceptance
- [ ] No internal caller builds a shell string; all use argv
- [ ] The `shell` tool's fate is decided and the decision recorded with its rationale
- [ ] Adversarial injection tests exist and pass, and fail on the previous commit
- [ ] `create_subprocess_shell` appears nowhere, or only in one deliberately sandboxed site
- [ ] The orchestrator lane still reaches a terminal phase
