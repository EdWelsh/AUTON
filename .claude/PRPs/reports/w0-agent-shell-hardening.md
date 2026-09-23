# Report: Agent Shell Hardening (H0)

**Plan**: `.claude/PRPs/plans/w0-agent-shell-hardening.plan.md`
**Source PRD**: `auton-hardware-truth.prd.md` — phase H0

## What was wrong

`base_agent.py` ran `asyncio.create_subprocess_shell()` on a string built by
interpolation. The plan named three call sites. There were **ten**: the two
internal ones, the `shell` tool, and seven SLM tool executors
(`_analyze_dataset`, `_tokenize_data`, `_train_model`, `_evaluate_model`,
`_quantize_model`, `_export_gguf`, `_export_onnx`) that each built
`f"python SLM/scripts/….py --checkpoint {path}"` from model-supplied paths.

Every one was reachable from model output. A `test_name` of `x; touch /tmp/pwned`
ran the touch. So did a dataset path, a checkpoint path, a make target
containing a newline, and a workspace directory whose name contained `$(...)`.

## Task 2 decision: the `shell` tool is kept, behind an allowlist

The plan offered remove / allowlist / sandbox, and recommended **remove** on the
evidence that the measured 8/8 tool-calling run used only specific tools.

**Chosen: allowlist** (option 2). The measurement is real but narrow — it covered
the kernel-build lane, and never exercised an SLM-mode agent. Removing a tool
those agents may depend on, on evidence that never ran them, trades a loud
failure for a silent one. The allowlist closes the injection either way; what it
adds over removal is that an agent reaching for something outside it is
**refused by name**, so a genuine need appears in a log instead of as an agent
quietly failing to do its job.

The tool is no longer a shell. `shlex.split` turns the command into argv and the
program's basename must be in the allowlist. `make all; touch x` is not two
commands — it is `make` with three nonsense targets.

`SHELL_ALLOWLIST` lives in `llm/tools.py` next to the schema, and `base_agent`
imports it. The tool description is generated from the set, so the model is never
invited to run something the executor will refuse. Three tests pin that agreement.

What this does **not** bound: what an allowlisted program can be told to do.
`git` and `make` can still reach outside the workspace. A goal drawn from
untrusted text still warrants a sandbox — recorded in the header of
`scripts/orchestrate-native.sh`, which previously carried a now-stale warning
about `_run_shell`.

## Verification

| Check | Result |
|---|---|
| `create_subprocess_shell` anywhere in `agent/` | none — `_run_shell` deleted |
| Adversarial tests | 28 in `tests/unit/agents/test_base_agent_injection.py` |
| Same tests on the previous commit | 13 fail, **7 by executing the injected command** |
| Full unit suite | 834 pass |
| Agent-facing output shape | byte-identical to the shell path, success and failure, pinned by test |

## Task 4: the lane reached a terminal phase but did not exercise the new path

`scripts/orchestrate-native.sh` against a serial.h goal reached
`Orchestration failed` in 1 iteration — terminal, which is the plan's bar.

It proves less than the plan assumed. **Zero `[exit code:` lines**: the local
model never called `build_kernel` or `run_test`. The architect registration from
plan w0-scheduler-dispatch worked (serial-001 was assigned and executed), but the
reviewer rejected the output — gemma4 wrote a whole serial driver for a
one-line-comment task — and both tasks blocked.

So the output-shape contract is **not** held by the lane. It is held by the
direct old-vs-new comparison above and by
`TestOutputShapeIsUnchanged`. Recorded rather than glossed: a green lane here
would have been green without the change.

## Follow-on

- The reviewer rejecting a trivially-scoped task because the model over-built it
  is a task-decomposition problem, not a shell problem. Belongs with the
  workspace-isolation work already queued for F6.
- `except Exception` in `_execute_tool` turns any internal breakage into a string
  the agent reads as an ordinary tool failure. It hid a deleted-method bug during
  this work. `TestSlmToolsCannotBeInjected` now asserts no tool returns an
  internal error, but the swallow itself is still there.
