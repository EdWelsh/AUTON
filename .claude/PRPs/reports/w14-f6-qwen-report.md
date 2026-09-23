# Report: F6 (TFTP service) on a qualified model — the first agent-authored service that passes its gate

**Pre-registration**: `w14-f6-qwen-preregistration.md`, 2026-09-22T19:53:25Z, before the run
**Artifacts**: `.artifacts/authorship/2026-09-22-f6-qwen27b/`
**Model**: `ollama_chat/qwen3.5:27b`, qualified 4/4 by `scripts/model-probe.py`
**Run**: 20:12:20Z → 23:08:58Z (2 h 56 m), 2 iterations, $0.00

## Result

**An agent wrote a 430-line TFTP server that passes all 31 checks of the frozen gate suite,
having never seen it.** The workspace contained no `tests/` directory; the only mention of
`tftp_test.c` in the transcript is the goal text naming the file the agent was asked to write.

| | F4 (human control) | F6, gemma4 (w13) | **F6, qwen3.5:27b** |
|---|---|---|---|
| Implementation | 401 lines | 0 | **430** (`server.c` 376, `serve.c` 54) |
| Tests written | 255 lines, 24 cases | 0 | **0** — the task never ran |
| Gate, as frozen | n/a | exit 2: not generated | **exit 1: compile failure** |
| Gate, corrected | n/a | n/a | **exit 0: 31/31 pass** |
| Where it stopped | n/a | tool confusion, turn cap | the turn cap, mid-task |

Both gate lines are reported because both are true, and the difference is the finding.

## The frozen gate was wrong, and it would have buried the result

As frozen, the gate failed the build on `NULL`, `kmemcpy` and `kstrcmp` — none of them the
agent's fault:

`tests/kernel/tftp_stub/include/kernel.h` sits ahead of the tree's own headers on the include
path, so it **shadows the real `kernel/include/kernel.h` entirely**. It declared `kprintf` and
nothing else. The real header also declares `kmemset`, `kmemcpy`, `kstrlen` and `kstrcmp`, which
is what a TFTP server naturally calls — so **no spec-conformant implementation using libk could
ever have compiled under this gate**. The suite's own reference avoided those functions, so its
self-test passed and the defect stayed invisible until something real met it.

Fixed: the stub now declares libk exactly as the real header does, and `tftp_stub/libk.c`
defines the four for the host build. The self-test still passes, and the agent's unmodified
`server.c` then passes 31/31. The archived copy is byte-identical to what ran.

## The engine had already thrown the work away

The run ended `tftp-002 failed (no output: branch agent/dev-01/services-002 is identical to
main)` — while `server.c` sat untracked in the working tree.

`commit_pending()` only committed when the agent's branch happened to be checked out.
`checkout_main()` commits before leaving, so that path was safe; `merge_branch()` checks out
main **directly**, and after it the agent's files belonged to no branch at all. Fixed in
`d1b3d00`, with two tests that fail without it.

Two harness defects, both of which made a working implementation look like nothing.

## What the model actually did

```
manager    : read_spec ×3, list_files ×3            -> 5 tasks
architect  : read_file ×18, search_code ×4, write_file ×6, edit_file
             -> arch-services MERGED; arch-tests NOT ADOPTED (did not compile)
dev-01     : read_spec ×2, read_file ×12, list_files ×9, search_code,
             write_file ×3, build_kernel ×2, shell ×3, git_commit, git_diff
             -> tftp.h reviewed and MERGED; server.c + serve.c written
reviewer-01: read_spec, read_file ×2, git_diff      -> approved on the diff
integrator : read_file ×9, build_kernel ×4, edit_file ×4, search_code ×2
```

It explored the tree before writing, cited the RFCs in its header comment (`RFC 1350` with the
`RFC 1123 §4.2.3.1` fix), matched the spec's file sizes and block size, and built as it went.

## What it did not do, and what that costs

- **No tests.** `tftp-002` onward never completed, so the measured authorship is
  implementation-only: 430 lines of code, 0 of tests. The PRD's question — whether an agent's
  *own* verification is any good — is still unanswered.
- **Scope creep.** The architect rewrote `kernel/include/slm.h` (+709 lines) and added a
  266-line design note for a TFTP goal. It compiled, so the design gate adopted it.
- **Slow.** 2 h 56 m produced two merges. At ~500 s a call with a full spec in the prompt, the
  20-turn cap is reached in wall-clock terms long before the task is finished.
- **One design was refused** for not compiling, which is the gate working.

## Injected bugs, on the agent's own code

The protocol's step 5, run against `server.c` as written:

| Injected into the agent's server | Caught |
|---|---|
| block counter never incremented | yes |
| TID check removed (any sender can drive the transfer) | yes |
| retry limit raised to 65535 (never abandons) | yes |
| **ACK for a block never sent is accepted** | **no — a gap in the human suite** |
| duplicate-ACK branch disabled | not a defect: the fall-through also sends nothing |

**4 of 5 before, 5 of 5 after.** `tftp.md`'s ACK rule 4 ("any other block number → ignore") had
no case in the frozen suite, and accepting an out-of-range ACK advances the transfer past blocks
the client never received — silent data loss. Two cases now cover it (`f3170bd`); the reference
and the agent's unmodified code both still pass.

A gap in a human-written suite, found by injecting bugs into agent-written code. That is the
method working in the direction nobody planned for.

## What this changes

The bottleneck is no longer "the model cannot do this". It is turns and time: the tasks after
the implementation never ran. The next run should give the developer more turns, and the
faster qualified model (`qwen3.5:9b`, 285 s slowest) is worth trying on the same goal for
comparison — both are single commands (`docs/GENERATION-QUEUE.md`).

The honest headline: **an agent-written service passed a suite written by a person, which it
never saw — and the only reason that was not visible on the day is that the suite and the
engine each had a bug.**
