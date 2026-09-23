# Report: V8 Re-run (virtio-console, agent-authored), gemma4

**Plan**: `plans/completed/w13-driver-v8-rerun.plan.md` · **Pre-registration**:
`w13-driver-v8-rerun-preregistration.md` (16:45:31Z, before the run) · **Artifacts**:
`.artifacts/authorship/2026-09-22-v8-rerun/`

## Result: one record, which the validator refuses. Nothing else

| Deliverable / gate (pre-registered order) | Result |
|---|---|
| (2) record `spec/drivers/virtio-console.md` | **written and merged; `driver_spec.py --validate`: INVALID, no front-matter block** |
| (3) reference `tests/kernel/virtio_console_reference.c` | not written. **Gate suite (29 checks, `242ee08`): exit 2, not generated** |
| (1) spec section in `drivers.md` | not written |
| (4) the agent's own tests and runner | not written |
| Injected bugs against the agent's tests | not applicable: no agent tests (V5 6/6 and V6 5/5 stand alone) |
| Status cap `specified` | held trivially: the record states `Status: Not Implemented` in prose, and there is no front matter |

Run 16:45:37Z to 16:51:36Z, 6 minutes, 3 iterations. Harness (`measure_authorship.sh`): record
present; reference_new 0; tests 0; spec section missing. The 167 "reused" lines are the
experiment's own inputs.

## What the agents did

```
design (architect): read_spec(drivers) → write_file(driver_defs.h, 2847 bytes)
                    → NOT ADOPTED: does not compile (the new gate, first time live)
virtio-003 (dev): write_file(spec/drivers/virtio-console.md) ×2 → git_commit → reviewed → MERGED
virtio-004 (dev): read_file(spec/subsystems/drivers.md) ×3 → no output → FAILED
virtio-005 (dev): read_spec('dev/virtio-console') → refused (kind 'dev') → no output → FAILED
```

This run went furthest of the four gemma4 runs today: the developer used `write_file` and
`git_commit` correctly, and the loop merged the result. What it wrote is prose in the
**shape** of a record, with none of the format `drivers/README.md` defines: no front matter,
no devices, no mechanical verification entries. Its "test cases" are prose ("check for data
integrity").

## Loop findings

| Finding | Fix |
|---|---|
| The design phase refused a non-compiling header | working as intended: `_adopt_design` (`202db69`), first live refusal |
| **The reviewer approved a record the validator refuses** | the pre-review gate now loads every changed `drivers/<name>.md` with `driver_spec`, and a refusal becomes the review (`ae61438`). All real records pass it; this one is kept as a fixture |

## The gate suite, for when a capable model runs this

`tests/kernel/run_virtio_console_gate_test.sh` was frozen before the run: 29 checks from VIRTIO
1.2 §5.3 against the interface `virtio_console_gate/include/virtio_console.h` (in the workspace).
The test itself was not in the workspace. It is proved on a human reference, and catches 8 of 8
injected bugs: receive buffers device-readable, transmit buffers device-writable, MULTIPORT
accepted, used length trusted, size read when not negotiated, big-endian size, zero-length
buffers accepted, completion not freeing.

## Conclusion

The same as F6, generate-mm and storage: no verified line. The loop keeps getting stricter about
what it merges. What's left is the model, and choosing a capable model is the owner's decision.
