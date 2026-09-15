---
service: dhcp
requires: [netif, ethernet, ipv4, udp, allocator, klog, terminal, scoped]
excludes: [tcp, fs, preemptive, ipc]
entry: dhcp_serve
markers:
  - "[DHCP] listening on :67"
  - "[DHCP] DISCOVER from 52:54:00:12:34:56"
  - "[DHCP] OFFER 10.0.2.100"
  - "[DHCP] REQUEST for 10.0.2.100"
  - "[DHCP] ACK 10.0.2.100 lease 3600s"
assets: []
---

# DHCP Server Service Specification

## Overview

Serves IPv4 addresses from a fixed pool to clients on the local link, per
**RFC 2131** (DHCP) and **RFC 2132** (options). One UDP socket, one lease table, one
serve loop — no threads, no filesystem, no persistence across boots.

The retired tree implemented a DHCP *client* (`net/dhcp.c`), so the wire format and option
encoding are already specified in [`../subsystems/net.md`](../subsystems/net.md). This spec
describes only the server side: what to do with a packet once parsed, and what state to keep.

Scope boundary: this serves a single subnet with no relay agents (RFC 2131 §4.3.1 `giaddr`
must be zero; a non-zero `giaddr` is dropped and logged). Relay support would need routing,
which the service excludes.

## Data Structures

### Lease

```c
typedef struct {
    uint8_t  mac[6];        /* client hardware address (chaddr) */
    ipv4_t   ip;            /* host order, as everywhere in net.h */
    uint32_t expires_at;    /* uptime seconds; 0 = free */
    uint32_t xid;           /* transaction of the in-flight OFFER, else 0 */
    uint8_t  state;         /* LEASE_FREE | LEASE_OFFERED | LEASE_BOUND */
} dhcp_lease_t;
```

### Server state

```c
#define DHCP_POOL_MAX 32

typedef struct {
    ipv4_t       pool_base;     /* first assignable address */
    uint32_t     pool_count;    /* <= DHCP_POOL_MAX */
    ipv4_t       netmask;
    ipv4_t       gateway;       /* option 3; 0 to omit */
    ipv4_t       dns;           /* option 6; 0 to omit */
    uint32_t     lease_secs;    /* option 51 */
    dhcp_lease_t leases[DHCP_POOL_MAX];
} dhcp_server_t;
```

The pool is fixed at compile time. A growable pool would need the allocator on the packet
path, and a service that can fail to answer because it is out of memory is worse than one
that answers "no addresses left".

## Interface (`kernel/include/dhcp.h`)

```c
/* Configure the pool. Returns -1 if pool_count > DHCP_POOL_MAX. */
int  dhcp_server_init(const dhcp_server_t *cfg);

/* The single serve loop. Binds UDP :67, polls, never returns.
 * This is the `entry` named in the front-matter. */
void dhcp_serve(void);

/* One packet in, zero or one packet out. Separated from the loop so it is
 * testable without a NIC — the property a serve loop otherwise destroys. */
int  dhcp_handle(const uint8_t *frame, uint32_t len);

/* Reap expired leases. Called from the loop on each tick. */
void dhcp_expire(uint32_t now_secs);
```

## Behavior

### Serve loop

1. `dhcp_server_init` with the configured pool; log `[DHCP] listening on :67`.
2. Bind UDP port 67, broadcast-enabled.
3. Poll for a frame. On each iteration call `dhcp_expire(uptime_secs())`.
4. Pass each received frame to `dhcp_handle`.

No blocking, no sleeping: the service excludes `preemptive`, so the loop is the only thing
running and polling is the correct shape.

### DISCOVER → OFFER (RFC 2131 §4.3.1)

1. Validate: `op == BOOTREQUEST`, `htype == 1`, `hlen == 6`, magic cookie `0x63825363`,
   option 53 == 1. Anything else is dropped and counted.
2. Drop if `giaddr != 0` — no relay support (see Scope boundary).
3. If a lease already exists for `chaddr`, re-offer the same address. A client that DISCOVERs
   twice must not consume two addresses.
4. Otherwise take the first `LEASE_FREE` entry. If none, log and drop — do **not** offer an
   address already bound.
5. Record `state = LEASE_OFFERED`, `xid`, and `expires_at = now + OFFER_TIMEOUT` (60s) so an
   abandoned offer returns to the pool.
6. Reply OFFER: `yiaddr` = the address, option 53 = 2, option 54 = server id, option 51 =
   `lease_secs`, options 1/3/6 for netmask/gateway/DNS where non-zero.
7. Log `[DHCP] OFFER <ip>`.

Broadcast the reply to 255.255.255.255 unless the client set the broadcast flag to zero *and*
supplied a `ciaddr` — the client has no address yet, so unicast requires ARP the client cannot
answer.

### REQUEST → ACK / NAK (RFC 2131 §4.3.2)

1. Match on `chaddr` and the requested address (option 50, else `ciaddr`).
2. No matching lease, or a lease offered to a different `xid` → **NAK**. A silent drop leaves
   the client retrying for its full timeout.
3. Otherwise `state = LEASE_BOUND`, `expires_at = now + lease_secs`, clear `xid`.
4. Reply ACK with the same options as the OFFER.
5. Log `[DHCP] ACK <ip> lease <n>s`.

### RELEASE and DECLINE

RELEASE (option 53 == 7) frees the lease. DECLINE (== 4) frees it and marks the address
unusable until restart — the client found it already in use, which means something outside
the pool holds it.

### Expiry

`dhcp_expire` frees every lease whose `expires_at` has passed. `LEASE_OFFERED` entries expire
at 60s, `LEASE_BOUND` at `lease_secs`. Uptime is monotonic and never wraps within any plausible
uptime, so no wrap handling is specified.

### Edge cases

| Case | Behaviour |
|---|---|
| Pool exhausted | Log, drop. No reply is correct; NAK would be a lie about *this* request |
| Frame shorter than the BOOTP header | Drop, count as malformed |
| Option block unterminated (no 0xFF) | Parse what is complete, ignore the remainder |
| Option length overruns the frame | Drop — a length field trusted past the buffer is the classic parser hole |
| Duplicate DISCOVER, same xid | Re-send the same OFFER, idempotent |
| REQUEST for an address outside the pool | NAK |

## Files

| Path | Contents |
|---|---|
| `kernel/include/dhcp.h` | The interface above |
| `kernel/services/dhcp/server.c` | `dhcp_server_init`, `dhcp_handle`, `dhcp_expire` |
| `kernel/services/dhcp/serve.c` | `dhcp_serve` — the loop and nothing else |

Split so `dhcp_handle` is reachable from a test without a NIC.

## Dependencies

`scoped` is required because every AUTON image ships a manifest-scoped model and a chat
terminal — an image the user cannot ask anything is not what this OS is. It was missing from
this spec until the intent compiler generated a DHCP spec that included it and the two
disagreed (`.claude/PRPs/reports/w3-intent-manifest-to-service.md`).

Capabilities, per the front-matter: `netif`, `ethernet`, `ipv4`, `udp` from
[net](../subsystems/net.md); `allocator` from [mm](../subsystems/mm.md); `klog` and `terminal`
from [sys](../subsystems/sys.md).

Explicitly **not** required: `tcp`, `dns`, `dhcp-client`, `http-server` — optional net
capabilities this service never touches. `fs` is excluded: leases live in RAM and are lost on
restart, which RFC 2131 permits (§4.3.1 — a server may forget, clients re-REQUEST).

## Acceptance Criteria

1. All five `markers` appear on the serial console, in order, on a successful run.
2. A client on the same link obtains an address and can ARP for the gateway.
3. Two clients receive different addresses; one client DISCOVERing twice receives the same one.
4. A REQUEST for an unoffered address is answered with a NAK, not silence.
5. An abandoned OFFER returns to the pool within 60s.
6. A malformed option length is dropped without reading past the frame.
7. The built image contains no TCP and no filesystem code — the `excludes` are testable, and
   an image that violates them fails the build.
