---
service: tftp
requires: [netif, ethernet, ipv4, udp, e1000, allocator, klog, terminal, scoped, timer, uptime]
excludes: [tcp, fs, preemptive, ipc]
entry: tftp_serve
markers:
  - "[TFTP] listening on :69"
  - "[TFTP] RRQ pattern.bin octet"
  - "[TFTP] sent pattern.bin 1300 bytes in 3 blocks"
assets: []
---

# TFTP Server Service Specification

## Overview

Serves two built-in, read-only files over UDP, per **RFC 1350** (TFTP revision 2) with the
correction in **RFC 1123 §4.2.3.1** (the Sorcerer's Apprentice fix). One transfer at a time,
one serve loop, no filesystem: the files are generated in memory at init.

This is F6's service, chosen so the comparison with F4's DHCP server is fair. It uses the same
capabilities and the same UDP request/response shape. It cannot be copied from DHCP, because it
has what DHCP lacks: lock-step transfer state, retransmission on timeout, a short final block,
and error replies.

Scope boundary: **read requests in `octet` mode only.** WRQ is refused with an access-violation
error (there is nowhere to write). `netascii` is refused with error 0 and a message saying so,
because both files are binary and a netascii transfer would require CR/LF translation of bytes
that are not text. This is a stated deviation from RFC 1350 §1, which lists netascii as a mode.
No option extensions (RFC 2347 and later): an RRQ carrying options is served as if it had none,
which RFC 2347 §2 permits.

## Data Structures

### Files

```c
/* Generated at init, never written afterwards. byte[i] = i & 0xFF. */
#define TFTP_FILE_PATTERN_LEN 1300   /* "pattern.bin": 512 + 512 + 276, three DATA blocks */
#define TFTP_FILE_EXACT_LEN   1024   /* "exact.bin": 512 + 512 + a zero-length final block */
```

`exact.bin` exists because a file whose length is a multiple of 512 ends with an **empty** DATA
block (RFC 1350 §6). That is the case an implementation most often gets wrong.

### Transfer state

```c
#define TFTP_BLOCK        512
#define TFTP_TIMEOUT_MS   1000
#define TFTP_MAX_RETRIES  5

typedef struct {
    uint8_t   active;
    ipv4_t    peer_ip;
    uint16_t  peer_tid;      /* client's source port */
    uint16_t  our_tid;       /* server's port for this transfer, RFC 1350 §4 */
    const uint8_t *file;
    uint32_t  file_len;
    uint16_t  block;         /* last DATA block sent, 1-based */
    uint32_t  sent_at_ms;    /* when that block was (re)sent */
    uint8_t   retries;
} tftp_xfer_t;

/* What the pure handler asks the loop to transmit. len == 0 means send nothing. */
typedef struct {
    ipv4_t   dst_ip;
    uint16_t dst_port;
    uint16_t src_port;
    uint8_t  payload[4 + TFTP_BLOCK];
    uint32_t len;
} tftp_reply_t;
```

One transfer at a time. A second RRQ while a transfer is active gets ERROR 0 `"busy"` and does
not disturb the first. A server that interleaves transfers needs per-transfer state and a table
bound, which this service does not need.

## Interface (`kernel/include/tftp.h`)

```c
/* Generate the two files; reset transfer state. */
void tftp_server_init(void);

/* The single serve loop. Binds UDP :69, polls, never returns.
 * This is the `entry` named in the front-matter. */
void tftp_serve(void);

/* One UDP datagram in, zero or one reply out. No I/O: testable without a NIC.
 * dport is the port the datagram arrived on (69, or the transfer's our_tid). */
void tftp_handle(ipv4_t src, uint16_t sport, uint16_t dport,
                 const uint8_t *payload, uint32_t len, uint32_t now_ms,
                 tftp_reply_t *out);

/* Retransmit or abandon on timeout. Zero or one reply out. */
void tftp_tick(uint32_t now_ms, tftp_reply_t *out);
```

## Behavior

Opcodes, all big-endian 16-bit (RFC 1350 §5): RRQ 1, WRQ 2, DATA 3, ACK 4, ERROR 5.

### Serve loop

1. `tftp_server_init`; bind UDP port 69; log `[TFTP] listening on :69`.
2. Poll. Pass each datagram arriving on port 69 or on the active transfer's `our_tid` to
   `tftp_handle`, with `now_ms` from the timer.
3. Call `tftp_tick` on every iteration.
4. Transmit any reply with `len > 0` from `src_port` to `dst_ip:dst_port`.

Polling is the correct shape for the same reason it is in `dhcp.md`: the service excludes
`preemptive`, so the loop is the only thing running.

### RRQ (RFC 1350 §4, §5)

1. Parse `filename\0mode\0`. Both strings must be NUL-terminated **within the datagram**. A
   string running off the end is dropped, not answered: an unterminated string read past the
   buffer is this protocol's classic parser hole.
2. Mode compared case-insensitively. `octet` proceeds. `netascii` → ERROR 0
   `"netascii not supported"`. `mail` or anything else → ERROR 4.
3. Unknown filename → ERROR 1 `"file not found"`.
4. A transfer already active → ERROR 0 `"busy"`.
5. Otherwise start: `our_tid = 49152 + (transfer_count mod 16384)`, send DATA block 1, log
   `[TFTP] RRQ <name> <mode>`.

Every error reply is sent **from port 69** for an RRQ: no transfer was established, so no TID
exists (RFC 1350 §4).

### ACK

1. A datagram on `our_tid` from anything but `peer_ip:peer_tid` → ERROR 5 `"unknown transfer
   ID"` to the sender. The transfer is **not** affected (RFC 1350 §4).
2. ACK for `block`: if that block was the last (its DATA was shorter than 512 bytes, including
   empty), the transfer is complete. Log `[TFTP] sent <name> <len> bytes in <n> blocks`, go
   idle, send nothing. Otherwise send block `block + 1` and reset `retries`.
3. ACK for `block - 1` (a duplicate): **send nothing** (RFC 1123 §4.2.3.1). Retransmitting on a
   duplicate ACK is the Sorcerer's Apprentice bug: every block ends up sent twice, then four
   times, and the doubling continues for the rest of the transfer.
4. Any other block number → ignore.

### Timeout

`tftp_tick`: if active and `now_ms - sent_at_ms >= TFTP_TIMEOUT_MS`, resend the current block
and increment `retries`. After `TFTP_MAX_RETRIES` resends, abandon: log
`[TFTP] timeout <name> at block <n>` and go idle. Timeout-driven retransmission is the only
kind the server does.

### Other opcodes

WRQ → ERROR 2 `"read-only"`. DATA or ERROR on port 69 → drop. ERROR from the peer on
`our_tid` → abandon the transfer silently (RFC 1350 §7: an error is not acknowledged).

### Edge cases

| Case | Behaviour |
|---|---|
| Datagram shorter than 2 bytes | drop |
| ACK shorter than 4 bytes | drop |
| Filename or mode not NUL-terminated in the datagram | drop, never read past `len` |
| File length a multiple of 512 | final DATA block is empty (`exact.bin`: 3 blocks, the last 0 bytes) |
| Duplicate ACK | nothing sent |
| Stray packet from another TID mid-transfer | ERROR 5 to it; transfer continues |
| Second RRQ mid-transfer | ERROR 0 `"busy"` from port 69; transfer continues |

## Files

| Path | Contents |
|---|---|
| `kernel/include/tftp.h` | the interface above |
| `kernel/services/tftp/server.c` | `tftp_server_init`, `tftp_handle`, `tftp_tick` |
| `kernel/services/tftp/serve.c` | `tftp_serve`, which is the loop and nothing else |
| `tests/kernel/tftp_test.c`, `tests/kernel/run_tftp_test.sh` | host tests of `tftp_handle`/`tftp_tick` under ASan/UBSan, as `dhcp_test.c` does |

Split so `tftp_handle` is reachable from a test without a NIC.

## Dependencies

Capabilities, per the front-matter: `netif`, `ethernet`, `ipv4`, `udp`, `e1000` from
[net](../subsystems/net.md); `allocator` from [mm](../subsystems/mm.md); `klog`, `terminal` and
`uptime` from [sys](../subsystems/sys.md); `timer` from [drivers](../subsystems/drivers.md) for
retransmission; `scoped`, which every AUTON image carries (see `dhcp.md`).

`e1000` is listed from the start, not discovered at link time as it was for DHCP.

Explicitly **not** required: `tcp`, `dns`, `dhcp-client`, `http-server`. `fs` is excluded: the
files are generated in RAM.

## Acceptance Criteria

1. All three markers appear on the serial console, in order, when a client fetches
   `pattern.bin` in octet mode.
2. `pattern.bin` arrives as 1300 bytes in 3 blocks, byte `i` equal to `i & 0xFF`.
3. `exact.bin` arrives as 1024 bytes, and the transfer ends on an **empty** third block.
4. A duplicate ACK produces no DATA.
5. A stray datagram from another TID gets ERROR 5 and the transfer completes anyway.
6. An unterminated filename is dropped without reading past the datagram.
7. WRQ gets ERROR 2; `netascii` gets ERROR 0; an unknown file gets ERROR 1.
8. After 5 unanswered retransmissions the transfer is abandoned and the server accepts a new
   RRQ.
9. The built image contains no TCP and no filesystem code.
