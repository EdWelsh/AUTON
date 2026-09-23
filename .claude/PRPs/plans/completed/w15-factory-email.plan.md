# Plan: Service #6, Email Receive-and-Store (F11)

## Summary
The PRD scopes F11 to the honest MVP: **SMTP receive + mail storage on the filesystem, IMAP out
of scope**, with the success signal *"a real mail client delivers a message that survives a
reboot"* (`auton-service-kernel-factory.prd.md:388-392`). This plan specifies `services/smtp.md`
against RFC 5321's minimal server command set, stores each message as a file on FAT32, and
proves it with Python's `smtplib` (a standard client, not ours) and a second boot that lists the
stored mail.

## User Story
As a user who says "be an email server", I want an image that accepts mail for its domain and
still has it after a reboot, so that the email role is real at its smallest honest size.

## Problem → Solution
`roles.c:26-28`: *"needs SMTP/IMAP and mail storage"* → `smtp.md` (HELO/EHLO, MAIL, RCPT, DATA,
RSET, NOOP, QUIT), one file per message in `/MAIL/`, a size limit, local-domain-only relaying
(an open relay is refused by design), host tests, and a two-boot acceptance.

## Metadata
- **Complexity**: Large
- **Source PRD**: `auton-service-kernel-factory.prd.md` phase 11
- **Estimated Files**: 5 + generated service + report
- **Depends on**: `w13-generate-storage`, `w14-factory-fileserver` (FAT32 subdirectory handling, per the PRD's dependency on 8), `w14-factory-kvstore` (the flush-before-ack pattern)

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `w14-factory-kvstore.plan.md` | Task 1, Task 4 | the durability rule (flush before ack) and the two-boot acceptance, reused |
| P0 | `agent/kernel_spec/services/dhcp.md` | 60-145 | handle/serve split, edge tables |
| P1 | `agent/kernel_spec/subsystems/fs.md` | FAT32 | subdirectory creation must be in the w12 REQUIRED set; if it is not, add it there first |

## External Documentation
| Topic | Source | Key Takeaway |
|---|---|---|
| SMTP | RFC 5321 §4.1 (commands), §4.2 (replies), §4.5.3.1 (size limits), §4.5.2 (dot-stuffing) | the minimum server command set is exactly the 7 above plus VRFY (reply 252 is allowed) |
| Message format | RFC 5322 | stored verbatim; the server adds only a `Received:` header (RFC 5321 §4.4) |
| Client oracle | Python `smtplib` (stdlib) | `SMTP("127.0.0.1", 2525).sendmail(...)` against the hostfwd port |

GOTCHA: dot-stuffing. A line of `..` in DATA is a literal `.`. A server that fails to un-stuff it
corrupts messages silently, and one that treats `.\r\n` mid-line as the end truncates them.

## Patterns to Mirror
### DURABILITY
// SOURCE: w14-factory-kvstore.plan.md Task 1: reply success only after the write is flushed. Here that is `250` to DATA's end.
### EDGE_CASE_TABLE
// SOURCE: agent/kernel_spec/services/dhcp.md:135-145.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/kernel_spec/services/smtp.md` | CREATE | requires `tcp vfs fat32 writable virtio-blk …`; markers `[SMTP] listening on :25`, `[SMTP] stored <file> <bytes>`, `[SMTP] mailbox <n> messages` |
| `tests/kernel/smtp_test.c` + reference + runner | CREATE | state machine, dot-stuffing, limits, relay refusal |
| `scripts/run-storage-acceptance.sh` | UPDATE | `--service smtp`: `smtplib` sends 2 messages (one containing a `..` line) → clean halt → boot 2 → `[SMTP] mailbox 2 messages` → `mtype` a message and compare its body to what was sent |

## NOT Building
- IMAP/POP3, outbound delivery (MX lookup, queueing), SPF/DKIM/DMARC, STARTTLS, AUTH.

## Step-by-Step Tasks
### Task 1: Spec
- **ACTION**: The state machine table (reply codes per RFC 5321 §4.3.2); `RCPT` accepted only for `@<configured domain>`, otherwise `550 relay not permitted`; max message 1 MiB → `552`; max 16 recipients → `452`; a 5-minute idle timeout; file names `/MAIL/M<seq:07>.EML` (8.3-safe), the sequence persisted by scanning the directory at boot.

### Task 2: Host tests + reference
- **IMPLEMENT**: the happy path; commands out of order → `503`; dot-stuffing both ways; a `.` inside a line is not the terminator; oversize → `552` and nothing stored; relay → `550`; `RSET` mid-transaction clears the recipients.
- **VALIDATE**: `--self-test` PASS; injected: no un-stuffing, `250` before flush, relay allowed, sequence reset at boot (overwriting mail).

### Task 3: Build (protocol or human, labelled). Task 4: two-boot acceptance.

## Validation Commands
```bash
tests/kernel/run_smtp_test.sh --self-test
.venv/bin/python agent/tools/build_service.py smtp --tree <ws> --iso
scripts/run-storage-acceptance.sh <ws> --service smtp
```

## Acceptance Criteria
- [ ] `smtplib` delivers; the message survives a reboot byte-for-byte
- [ ] Not an open relay
- [ ] Dot-stuffing correct in both directions

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| FAT32 directory growth is untested | M | M | the dependency on F8's subdirectory work; add it to the w12 REQUIRED rules if missing |
| An open relay by accident | L | H | the relay-refusal test is a gate, not a nit |


---

## Progress: Tasks 1-2 (2026-09-22)

`smtp.md` + `run_smtp_test.sh` (32 checks, 9/9 injected bugs). Writing the tests corrected the spec: inside DATA, QUIT is body text. **Remaining**: Task 3 build, Task 4 two-boot acceptance with smtplib.


---

## Closed 2026-09-23

smtp.md and the 32-check suite (9/9) are done, as is the two-boot acceptance with smtplib. The build is a generation run.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
