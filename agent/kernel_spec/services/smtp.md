---
service: smtp
requires: [netif, ethernet, ipv4, tcp, vfs, fat32, writable, virtio-blk, allocator, klog, terminal, scoped, timer]
excludes: [ext2, preemptive, ipc, dhcp-client]
entry: smtp_serve
markers:
  - "[SMTP] listening on :25"
  - "[SMTP] stored /MAIL/M0000001.EML 482 bytes"
  - "[SMTP] 3 message(s) on disk"
assets: []
---

# SMTP Service Specification

## Overview

Accepts mail over SMTP on TCP 25 and stores each message as a file on the FAT32 volume. One
connection at a time.

**Scope, stated as a limit rather than discovered as a disappointment**: receive and store only.
There is no IMAP, no POP3, no outbound relay, no TLS, no authentication, and no queue. The PRD
scopes F11 to exactly this, and the success signal is the honest one: *a real mail client
delivers a message that survives a reboot*. An "email server" that cannot be read from is a
mail **sink**, and calling it that here is the point.

The client is the oracle: Python's `smtplib` speaks RFC 5321 and was not written for this
project, so a message it accepts as delivered is delivered.

## Commands (REQUIRED, RFC 5321 §4.1)

| Command | Reply | Notes |
|---|---|---|
| `EHLO <domain>` / `HELO` | `250 <our domain>` | `EHLO` answers with no extensions: none are offered, so none may be used |
| `MAIL FROM:<addr>` | `250 OK` | Resets any transaction in progress (§4.1.1.2) |
| `RCPT TO:<addr>` | `250 OK`, or `550 relay not permitted` | Only for the configured domain |
| `DATA` | `354` then `250 OK <seq>` | `250` only **after** the file is written and flushed |
| `RSET` | `250 OK` | Clears sender and recipients, keeps the session |
| `NOOP` | `250 OK` | |
| `QUIT` | `221 Bye` | Closes |
| anything else | `500 command not recognized` | |

Out of order is `503 bad sequence of commands`: `RCPT` before `MAIL`, `DATA` before `RCPT`,
`MAIL` inside a transaction that already has data. A client that gets `250` for a command that
could not have worked will deliver into a void and report success.

## Limits (REQUIRED, each refused by its own code)

| Limit | Value | Reply |
|---|---|---|
| Message size | 1 MiB | `552 message exceeds 1048576 bytes` |
| Recipients per transaction | 16 | `452 too many recipients` |
| Line length | 1000 bytes (§4.5.3.1.6) | `500 line too long` |
| Idle | 5 minutes (§4.5.3.2) | `421 timeout` and close |

**An oversize message stores nothing.** Not a truncated file: a partial message that looks like
a message is worse than no message.

## Relaying (REQUIRED)

`RCPT TO:` is accepted only when the address's domain matches the configured one, compared
case-insensitively. Everything else is `550 relay not permitted`, including an address with no
`@`. This server never sends mail, so an accepted recipient it cannot deliver to is a lie.

## DATA and dot-stuffing (REQUIRED, §4.5.2)

The body ends at a line containing a single `.`. A line that begins with `.` is transmitted with
an extra `.` prepended, and the server **removes it** before storing. Both halves matter:

- Un-stuffing not done: every line starting with a dot gains one on disk, and a mail with a
  leading-dot line is silently corrupted.
- Terminator detected by substring: a body line containing `.` anywhere ends the message early,
  truncating it and leaving the rest to be parsed as commands.

A `CRLF.CRLF` is the terminator; a bare `\n.\n` is not, and is data.

## Storage (REQUIRED)

- One file per message: `/MAIL/M<seq:07>.EML`, e.g. `/MAIL/M0000001.EML`. Eight characters and
  a three-character extension, so the name is 8.3 and needs no long-name entry.
- **The sequence is recovered by scanning `/MAIL/` at boot** and continuing after the highest
  number found. A counter that restarts at 1 overwrites the mail that survived the reboot,
  which is the exact failure the two-boot acceptance exists to catch.
- The stored file is the message as received: the `DATA` body, un-stuffed, with the
  `Received:` trace header this server prepends (§4.4).
- `250` is sent only after the file is written **and flushed**. A `250` is a promise, and a
  client that receives one deletes its copy.

## Interface (`kernel/include/smtp.h`)

```c
/* Scan /MAIL/ and continue the sequence after the highest file found.
 * Returns the message count, or -1 when the volume is unwritable. */
int  smtp_init(const char *domain);

/* One line of input, one reply out. Pure: no socket, no clock, so the state
 * machine is testable without a NIC (dhcp.md's handle/serve split).
 * Returns the reply length, or 0 when the line was body data. */
int  smtp_handle(const char *line, uint32_t len, char *out, uint32_t out_cap);

/* The serve loop. Binds TCP 25, never returns. The front-matter `entry`. */
void smtp_serve(void);
```

## Edge cases

| Case | Behaviour |
|---|---|
| `RCPT` before `MAIL FROM` | `503`, and no recipient recorded |
| `MAIL FROM` twice | The second is `503`; the first transaction stands (§4.1.1.2 allows a reset, not a silent restart) |
| `RSET` mid-transaction | `250`, sender and recipients cleared, sequence untouched |
| A body line of `..` | Stored as `.` |
| A body line containing `.` not alone | Data, not a terminator |
| Empty `MAIL FROM:<>` | Accepted: a bounce has a null reverse-path (§4.5.5) |
| `QUIT` after `RCPT`, before `DATA` | `221`, and the transaction is discarded |
| `QUIT` **inside** `DATA` | It is body text, not a command. Between `354` and the terminator everything is data (§4.1.1.4), and a server that honours commands there can be made to truncate a message by its own contents |
| Connection dropped before `.` | Nothing stored |
| `/MAIL/` absent at boot | Created; if it cannot be, `[SMTP] volume unwritable` and the service exits rather than accepting mail it cannot keep |

## Verification

`tests/kernel/run_smtp_test.sh --self-test` runs the host suite against
`tests/kernel/smtp_reference/`: the state machine and its `503`s, the limits and their codes,
relay refusal, dot-stuffing both ways, and sequence recovery from a directory listing.
`KERNEL_TREE=<dir>` gates a generated `kernel/services/smtp/`: exit 2 not generated, exit 1 wrong.

The acceptance step is two boots of one image
(`scripts/run-storage-acceptance.sh --service smtp`): Python's `smtplib` delivers three
messages, the guest halts, and the second boot prints `[SMTP] 3 message(s) on disk` with the
files intact and numbered from 1. **Mail surviving a reboot is the whole claim.**
