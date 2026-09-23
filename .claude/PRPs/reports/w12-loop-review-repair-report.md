# Implementation Report: Loop Review Repair

**Plan**: `.claude/PRPs/plans/w12-loop-review-repair.plan.md`

## Summary

The plan named four defects from the w11 runs. Writing its end-to-end test found **two more**,
and the sixth was the deepest: **the developer path had never once completed.** Every successful
developer task crashed on its last line, sending a review request whose type was a string, and
was recorded as a failure. With all six fixed, a real engine (only the model scripted) takes a
two-task chain through a rejection, a revision, approval and a deterministic merge.

| # | Defect | Where | Fix |
|---|---|---|---|
| 1 | a task that created no branch reported `main` | `base_agent.py` `execute_task` | `branch` is the branch the agent created (`_task_branch`), else `None`; `None` → MERGED, no review |
| 2 | an empty diff was reviewed; the model invented code to reject | `engine._trigger_review` | `_handle_result`: uncommitted agent work is committed (excluding `.auton/`, `build/`); no changes → FAILED `no output` |
| 3 | `request_changes` → BLOCKED, terminal | `engine.py:446` | `TaskGraph.requeue` with the review in `data["review_feedback"]`, shown in the author's next prompt; FAILED after `max_review_rounds` (default 3) |
| 4 | the manager planned "read the spec" tasks; `read_spec` could not reach services/drivers/mitigations | `manager_agent`, `base_agent._read_spec` | `produces` required; `drop_undeliverable` removes tasks without it and remaps dependents transitively; `read_spec` takes `<kind>/<name>` with containment |
| **5** | **an approved task never reached MERGED in the graph**. The LLM integrator updated on-disk metadata only | `engine.py` dev loop | `_merge_approved`: `git merge --no-ff` by the engine; a conflict is requeued as feedback |
| **6** | **every successful developer task crashed**: `send_message(msg_type="review_request")`, and `Message.to_json` calls `.value` | `base_agent.send_message` | `MessageType(msg_type)` accepts either form |

Also: agent exceptions now log their traceback (defect 6 was invisible without it), and a failed
run returns `error` naming each unfinished task and its reason, where before there was
`Orchestration failed: unknown`.

## Validation

| Check | Result |
|---|---|
| `tests/unit/orchestrator/test_review_path.py` | 16 passed: each defect by name, with the w11 transcript quoted |
| `tests/unit/orchestrator/test_loop_completes.py` | a real engine, scripted model: read task dropped, k-001 rejected once then merged with the revision, k-002 merged, `error` names the failed build |
| agent suite | 1568 passed, 27 skipped |
| lint (new files) | clean |

## Not done here

- The plan's manual gemma4 run waits for `w12-kernel-base` (it needs a buildable workspace). It
  is folded into that plan's validation.
- `_trigger_review` still returns silently when no reviewer is free, leaving the task in REVIEW.
  With one reviewer and serial review that cannot happen today; noted for when reviewers run in
  parallel.

## Live validation on gemma4 (added after the plan's own checks)

The plan deferred a live run until `w12-kernel-base` existed. Three runs of the same goal ("add
a one-line comment at the top of kernel/include/kmath.h"), each exposing the next defect:

| Run | Outcome | Defect found → fix |
|---|---|---|
| 1 | the developer wrote **exactly the right diff**; review rejected it 3 times over a `kmath_add` function that exists nowhere; FAILED with that reason (not `unknown`) | **7**: the reviewer never called `git_diff`. The diff and the task brief are now in the review prompt, and a rejection citing no changed file is discarded as unfounded |
| 2 | hung 17 minutes on an Ollama connection with nothing in flight at the server | **8**: model calls had no timeout. Every call is bounded by `[llm].request_timeout` (600 s), with a named `ModelTimeoutError` |
| 3 | **`All tasks complete!`: the first change this loop has ever merged**, through review, onto `main` | **9**: the merge also carried a 255-line header the architect left uncommitted on its design branch, which survived `git checkout`. `checkout_main` now commits it on the branch that made it |

Run 3's final build failed because the run was started with the bare CLI, which does not source
the cross-toolchain (Apple clang cannot emit ELF64). That is harness setup, not the loop.
`scripts/orchestrate-native.sh` sources it, and the protocol in `w13-factory-f6-rerun` uses it.

The model also wrote the comment line twice, which is output quality, not a loop defect.
