# Report: Generate Storage (virtio-blk + FAT32, F7), gemma4

**Plan**: `plans/completed/w13-generate-storage.plan.md` · **Pre-registration**:
`w13-generate-storage-preregistration.md` (16:39:17Z, before the run) · **Artifacts**:
`.artifacts/authorship/2026-09-22-generate-storage/`

## Result: nothing generated

| Gate (pre-registered order) | Result |
|---|---|
| `run_virtio_blk_test.sh` (tree mode) | **exit 2: not generated** |
| `run_fat32_test.sh` (tree mode) | **exit 2: not generated** |
| `run-storage-acceptance.sh` | not reached |

Run 16:39:23Z to 16:42:09Z, 3 minutes of a 60-minute budget. The manager planned 4 developer
tasks. The first two ended `no output`, and the other two stayed pending behind them.

## What the agents did

```
design (architect): read_spec → write_file(kernel/include/drivers/common/driver_defs.h, 95 lines)
                    → left on agent/architect-01/arch-drivers, never merged (loop defect, below)
dev-001 (virtio-blk): read_spec(drivers/virtio-blk) → answered in text, no tool call → no output
dev-002 (fat32):      read_spec(fs)                 → answered in text, no tool call → no output
```

Unlike F6 and generate-mm, the developer did not call a spec function as a tool. It read the spec
once and stopped.

## Defects found in the loop (fixed after the run)

| Defect | Fix |
|---|---|
| The architect's design headers were never merged, so developers built from a main without them | `_adopt_design`: a design branch that changes something and compiles is merged before development (`202db69`) |

The stranded header would **not** have been adopted: 18 compile errors, including
`*/<TAB>ypedef uint32_t dev_id_t;`. This is the same shape as generate-mm's `ttypedef`: a `\t`
escape where `\n` + `t` was meant.

**Open observation, not a finding yet**: two files in two runs are corrupted the same way. A
direct probe (`ollama/` against `ollama_chat/`, one short file) decoded both correctly, but
`ollama/` silently dropped a requested leading tab. `ollama/` does tool calls by prompting the
model to write JSON as text. `ollama_chat/` uses Ollama's native tool calls. Switching providers
changes the experiment's loop, so it is noted here and not changed. The compile check catches
the corruption either way, and hands the errors back to the author.

## Harness made for this plan (committed before the run)

`scripts/run-storage-acceptance.sh` (`28d7b7d`): mformat a 512 MiB image with `SEED.TXT`, boot
it as virtio-blk (`cache=writethrough`, `-boot d`), wait for fs.md's markers, wait for QEMU to
exit, then `mtype ::AUTON.TXT` and `fsck.fat -n`. Against kernel-base-v5 it exits 2 and names
all five missing markers; the base still reaches `[BOOT] OK`. **Its positive path is unexercised**
until some tree prints the markers.

`provides: [fs]` in `virtio-blk.md` stays: in `device_drivers.py`, "fs" is the storage capability
(`ROLE_CAPS["storage"] = "fs"`), so the plan's proposed rename would break the mapping.

## Not applicable
Injected bugs, promotion to `implemented`, and source_map entries: there is nothing generated.

## Conclusion
Third generation run on gemma4 with zero working lines. The loop now compiles, adopts designs,
and returns compiler errors as review. The remaining gap is the model, and choosing a capable
one is the owner's decision.
