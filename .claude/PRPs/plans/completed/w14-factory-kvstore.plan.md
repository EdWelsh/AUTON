# Plan: Service #4, Persistent Key-Value Store (F9)

## Summary
`roles.c:29-30` advertises `database`/`sql` as roadmap, *"needs persistent storage and a query
engine"*. The PRD settles scope: a KV store, not SQL, with the role note corrected to match
(`auton-service-kernel-factory.prd.md:373-378, 424`). This plan specifies `services/kvstore.md`
speaking a **subset of RESP2**, the Redis serialisation protocol, so the protocol is citable and
an independent client (`redis-cli`) is the oracle. Data persists in an append-only log on FAT32
that is replayed at boot. Success: **values survive a reboot**.

## User Story
As a user who says "be a database", I want an image that stores keys and values over the network
and still has them after a reboot, so that the role does what its name says, honestly scoped.

## Problem → Solution
No database, and `roles.c` promises "a query engine" → `kvstore.md` (RESP2 subset: `PING`, `GET`,
`SET`, `DEL`, `EXISTS`, `DBSIZE`), an append-only log (`KV.LOG`) with a CRC per record replayed
on mount, host tests, and a two-boot acceptance with `redis-cli`.

## Metadata
- **Complexity**: Large
- **Source PRD**: `auton-service-kernel-factory.prd.md` phase 9
- **Estimated Files**: 5 spec/test + generated service + report
- **Depends on**: `w13-generate-storage` (FAT32 **with** `writable`), protocol from `w13-factory-f6-rerun`

---

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/kernel_spec/services/README.md` | all | format; rule 3 "cite protocols normatively" |
| P0 | `agent/kernel_spec/services/dhcp.md` | 60-145 | the handle/serve split, edge-case table style |
| P0 | `agent/kernel_spec/subsystems/fs.md` | FAT32 section (w12) | the write path under `writable` |
| P1 | base `kernel/slm/roles.c` | 22-32 | the row this closes (edited in F12, not here) |
| P1 | `scripts/run-storage-acceptance.sh` (w13) | all | extend with a two-boot mode |

## External Documentation
| Topic | Source | Key Takeaway |
|---|---|---|
| RESP2 | redis.io/docs/latest/develop/reference/protocol-spec | arrays of bulk strings in; `+OK`, `$-1` (nil), `:<int>`, `-ERR` out; inline commands allowed |
| redis-cli | Redis 7.x | `redis-cli -h 127.0.0.1 -p 6379 SET k v` speaks RESP2 by default (`-3` selects RESP3; do not use) |

KEY_INSIGHT: supporting inline commands (`PING\r\n`) as well lets `nc` test without a client
library. RESP2 requires both.
GOTCHA: inventory the RESP spec in `vendors.yaml` (publisher Redis Ltd, public docs). The spec
document's licence differs from Redis's server licence. Cite the protocol and copy no code.

## Patterns to Mirror
### SERVICE_SPEC
// SOURCE: agent/kernel_spec/services/dhcp.md:1-12 (front-matter), 65-81 (interface: `*_handle` pure, `*_serve` the loop)
### EDGE_CASE_TABLE
// SOURCE: agent/kernel_spec/services/dhcp.md:135-145
### TEST_STRUCTURE
// SOURCE: tests/kernel/dhcp_test.c:15-45: `ok()`, a fake clock, a `capture` sender.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/hardware/vendors.yaml` | UPDATE | inventory the RESP spec |
| `agent/kernel_spec/services/kvstore.md` | CREATE | requires `netif ethernet ipv4 tcp e1000 vfs fat32 writable virtio-blk allocator klog terminal scoped`; excludes `udp`-only services, `ext2`, `preemptive`, `ipc`; entry `kvstore_serve`; markers `[KV] replayed <n> records`, `[KV] listening on :6379`, `[KV] SET <key>` |
| `tests/kernel/kvstore_test.c`, `kvstore_reference/`, `run_kvstore_test.sh` | CREATE | parser, log replay, torn-record recovery |
| `scripts/run-storage-acceptance.sh` | UPDATE | `--service kvstore`: boot 1 → `redis-cli SET` ×3, `DEL` ×1 → guest halts → boot 2 → `GET` the survivors, check the deleted key is nil |
| `agent/kernel_spec/services/README.md` | UPDATE | table row |

## NOT Building
- SQL, transactions, `EXPIRE`, pub/sub, RESP3, auth.
- Compaction of the log (a stated limitation, with a size cap and a refusal when reached).

## Step-by-Step Tasks
### Task 1: Spec
- **ACTION**: `kvstore.md` with: the command table (arity, reply types); limits (key ≤ 256 B, value ≤ 4 KiB, ≤ 1024 keys, log ≤ 8 MiB, each refused with `-ERR` naming the limit); log record = `u32 len | u8 op | key | value | u32 crc32`; replay stops at the first bad CRC and truncates there, logging the byte offset (a torn write after power loss must not poison the store); fsync rule: a `SET` replies `+OK` only after the record is written and flushed.
- **VALIDATE**: `service_spec.py --validate/--resolve` OK.

### Task 2: Host tests + reference
- **IMPLEMENT**: RESP array parse; inline parse; a partial frame across two reads; oversize bulk → `-ERR` without buffering it; unknown command → `-ERR unknown command`; replay of 3 records; replay with a torn final record → 2 records, log truncated; `DEL` then replay → absent; a limit reached → refusal.
- **VALIDATE**: `--self-test` PASS; injected: no CRC check, reply before flush, parse across frames broken, off-by-one in the bulk length.

### Task 3: Build (protocol, or human fallback labelled)

### Task 4: Two-boot acceptance with redis-cli
- **GOTCHA**: The guest must halt cleanly (the log flushed) before the image is reused. Use a `SHUTDOWN` command (RESP has one) that flushes, prints `[KV] clean shutdown`, and halts.
- **VALIDATE**: boot 2 prints `[KV] replayed 4 records` (3 SET + 1 DEL); `GET` values match.

## Validation Commands
```bash
tests/kernel/run_kvstore_test.sh --self-test
.venv/bin/python agent/tools/build_service.py kvstore --tree <ws> --iso
scripts/run-storage-acceptance.sh <ws> --service kvstore
```

## Acceptance Criteria
- [ ] `redis-cli` values survive a reboot
- [ ] A torn final record is recovered, not fatal
- [ ] Every limit refused with a named `-ERR`
- [ ] The role note's correction is recorded for F12

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Users read "database" as SQL | M | L | F12 corrects the role text: "key-value store (RESP subset)" |
| The log grows without bound | M | M | a hard cap with a refusal; compaction named as future work |


---

## Progress: Tasks 1-2 (2026-09-22)

`kvstore.md` (RESP2 subset, CRC'd append-only log) and `run_kvstore_test.sh` (31 checks, 9/9 injected bugs; the reference models written and flushed separately so 'reply before flush' is testable). **Remaining**: Task 3 build, Task 4 two-boot acceptance with redis-cli.


---

## Closed 2026-09-23

kvstore.md and the 31-check suite (9/9) are done, as is `run-storage-acceptance.sh --service kvstore`. The build is a generation run.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
