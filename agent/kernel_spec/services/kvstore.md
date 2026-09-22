---
service: kvstore
requires: [netif, ethernet, ipv4, tcp, vfs, fat32, writable, virtio-blk, allocator, klog, terminal, scoped]
excludes: [ext2, preemptive, ipc, dhcp-client]
entry: kvstore_serve
markers:
  - "[KV] replayed 4 records"
  - "[KV] listening on :6379"
  - "[KV] clean shutdown"
assets: []
---

# Key-Value Store Service Specification

## Overview

A key-value store that speaks a **subset of RESP2**, the Redis serialisation protocol, over TCP
6379, and keeps its data in an append-only log on the FAT32 volume, replayed at boot.

**Why RESP2 and not something invented**: the protocol is published and stable, and an
independent client (`redis-cli`) becomes the oracle. A bespoke protocol would be tested only by
its own implementation, which is how a service passes its tests and fails every real client.
The protocol is **cited, never copied**: no Redis source is read or vendored, and Redis's server
licence is irrelevant to speaking its wire format.

**Why this is not a database.** `roles.c` advertises `database`/`sql` as needing "a query
engine". This service has no query engine, no SQL, no transactions, no expiry and no pub/sub,
and the role note is corrected to say so (F12). It stores values and returns them after a
reboot, which is what the PRD asked for and all it claims.

## Commands (REQUIRED, exactly these)

| Command | Arity | Reply on success | Notes |
|---|---|---|---|
| `PING` | 0 or 1 | `+PONG` or the echoed bulk | inline `PING\r\n` must work |
| `SET key value` | 2 | `+OK` | only **after** the record is written and flushed |
| `GET key` | 1 | bulk string, or `$-1\r\n` when absent | |
| `DEL key` | 1 | `:1` or `:0` | appends a delete record |
| `EXISTS key` | 1 | `:1` or `:0` | |
| `DBSIZE` | 0 | `:<count>` | live keys, not log records |
| `SHUTDOWN` | 0 | no reply | flush, print `[KV] clean shutdown`, halt |

Anything else is `-ERR unknown command '<name>'`. Wrong arity is
`-ERR wrong number of arguments for '<name>' command`. The error strings matter: `redis-cli`
prints them, and a client distinguishes them from a dropped connection.

`SHUTDOWN` replying nothing is deliberate — the acceptance harness needs the guest to stop with
the log flushed, and a reply the client never reads is worse than none.

## Protocol (REQUIRED, RESP2)

Requests are arrays of bulk strings (`*2\r\n$3\r\nGET\r\n$1\r\nk\r\n`), and **inline commands**
(`PING\r\n`) are also accepted, as RESP2 requires; inline lets `nc` drive the service with no
client library.

- A frame may arrive **split across reads**. The parser keeps its partial state and returns
  "incomplete" rather than erroring: TCP does not preserve message boundaries, and a parser that
  assumes it does works in tests and fails on a real network.
- A bulk length above the value limit is refused with `-ERR` **without buffering the bytes**.
  Reading them first is a remote memory-exhaustion primitive.
- A negative or non-numeric length, a missing CRLF, or an array header whose element count is not
  matched by the elements, is a protocol error: reply `-ERR protocol error` and close.

## Limits (REQUIRED, each refused by name)

| Limit | Value | Refusal |
|---|---|---|
| Key length | 256 bytes | `-ERR key exceeds 256 bytes` |
| Value length | 4096 bytes | `-ERR value exceeds 4096 bytes` |
| Live keys | 1024 | `-ERR key limit 1024 reached` |
| Log size | 8 MiB | `-ERR log full (8 MiB); compaction is not implemented` |

The log is never compacted. That is a limitation, stated here and refused explicitly when
reached, rather than a surprise at an unpredictable moment.

## The log (REQUIRED)

`/AUTON.KV` on the FAT32 volume. Each record:

```
u32  len        bytes that follow, excluding this field and the crc
u8   op         1 = SET, 2 = DEL
u8   key_len
u16  value_len  0 for DEL
u8[] key
u8[] value
u32  crc32      IEEE 802.3 polynomial 0xEDB88320, over every byte from `len` to the value
```

- A `SET` replies `+OK` **only after** the record is written through to the volume
  (`fs.md`: every mutation is written through before the call returns). A reply sent before the
  flush is a lie a client will believe and act on.
- **Replay stops at the first bad CRC or short record, and truncates the log there**, logging
  the byte offset: `[KV] truncated at offset <n>: bad crc`. A torn final record is what a power
  loss leaves behind; it must cost the last write, never the store.
- Replay applies records in order, so the last `SET` of a key wins and a `DEL` removes it.
  `[KV] replayed <n> records` counts **records applied**, not live keys.

## Interface (`kernel/include/kvstore.h`)

```c
/* Replay /AUTON.KV into memory. Returns records applied, or -1 if the volume
 * is unreadable. Truncates the log at the first bad record. */
int  kv_replay(void);

/* One request in, one reply out. Pure: no socket, no clock, so the parser and
 * the command semantics are testable without a NIC — the property a serve loop
 * otherwise destroys (dhcp.md's handle/serve split).
 *
 * Returns the reply length written to `out`, 0 when the request is incomplete
 * (more bytes needed), or -1 on a protocol error (the caller closes). */
int  kv_handle(const uint8_t *in, uint32_t in_len, uint8_t *out, uint32_t out_cap,
               uint32_t *consumed);

/* The serve loop. Binds TCP 6379, replays first, never returns.
 * This is the `entry` named in the front-matter. */
void kvstore_serve(void);
```

`consumed` is how a caller advances its buffer after a complete frame, and is how a partial
frame survives to the next read.

## Edge cases

| Case | Behaviour |
|---|---|
| Frame split mid-bulk across two reads | `kv_handle` returns 0, `consumed` 0; the caller appends more bytes |
| Two complete commands in one read | Handle the first, set `consumed` to its length; the caller calls again |
| `GET` of a key never set | `$-1\r\n` (nil), not an error |
| `DEL` of a key never set | `:0`, and **no** log record: an absent key's deletion changes nothing |
| `SET` of an existing key | A new record; replay's last-wins makes it current |
| Bulk length larger than the value limit | `-ERR value exceeds 4096 bytes`, bytes not buffered |
| Inline command with trailing spaces | Split on whitespace, empty tokens ignored |
| Log full | `-ERR log full`, and the store keeps serving reads |
| Volume unwritable at boot | `[KV] volume unwritable; refusing to serve` and the service exits, rather than serving data it cannot persist |

## Verification

`tests/kernel/run_kvstore_test.sh --self-test` runs the host suite against
`tests/kernel/kvstore_reference/`: RESP array and inline parsing, a frame split across reads,
oversize refusals, unknown and wrong-arity commands, CRC-checked replay, a torn final record
truncated at its offset, and every limit's refusal string. `KERNEL_TREE=<dir>` gates a generated
`kernel/services/kvstore/`: exit 2 not generated, exit 1 wrong.

The acceptance step is two boots of one image (`scripts/run-storage-acceptance.sh --service
kvstore`): `redis-cli` sets three keys and deletes one, `SHUTDOWN` halts the guest cleanly, and
the second boot prints `[KV] replayed 4 records` and returns the surviving values — with the
deleted key nil. **Values surviving a reboot is the whole claim**, and it is checked by a client
this project did not write.
