---
service: ssh
requires: [netif, ethernet, ipv4, tcp, vfs, fat32, allocator, klog, terminal, scoped, timer]
excludes: [writable, ext2, preemptive, ipc]
entry: ssh_service_main
markers:
  - "[SSH] listening on 22"
  - "[SSH] session opened"
assets: []
---

# SSH Service

An SSH server whose only channel is the AUTON chat terminal. One algorithm per slot, no
negotiation beyond accepting or refusing what the client offers.

**Why this exists at all**: the factory PRD pre-committed the outcome — *either an interactive
SSH session into the AUTON chat, or a written decision not to hand-roll crypto*. The crypto gate
(`kernel_spec/decisions/ssh-crypto.md`) returned **GO**, with every primitive coming from a
vetted third-party source. **No cryptographic primitive is written in this repo.** A primitive
that fails its vectors is a CUT, not a rewrite.

## Algorithms (REQUIRED, exactly these)

| Slot | Value | Source |
|---|---|---|
| Key exchange | `curve25519-sha256` | RFC 8731 |
| Host key | `ssh-ed25519` | RFC 8709 |
| Cipher (both directions) | `chacha20-poly1305@openssh.com` | OpenSSH `PROTOCOL.chacha20poly1305` |
| MAC | implicit in the cipher (AEAD) | as above |
| Compression | `none` | RFC 4253 §6.2 |

A client offering none of these gets `SSH_MSG_DISCONNECT` with reason
`SSH_DISCONNECT_KEY_EXCHANGE_FAILED` (3) and a plain reason string. The server **never** falls
back, and never offers an algorithm it does not implement.

## Version exchange (REQUIRED)

The identification string is `SSH-2.0-AUTON_0.1` followed by CR LF (RFC 4253 §4.2). Both sides'
strings, **without** CR LF, are `V_C` and `V_S` in the exchange hash. A line longer than 255
bytes, or one that does not begin `SSH-2.0-`, is a disconnect, not a truncation.

## Binary packet protocol (REQUIRED, RFC 4253 §6)

```
uint32  packet_length            (not including this field or the MAC)
byte    padding_length           >= 4
byte[]  payload                  packet_length - padding_length - 1
byte[]  random padding           padding_length
```

- `4 + packet_length` is a multiple of **8** before the cipher is in place, and of the cipher's
  block size after (8 for chacha20-poly1305, which sets the same bound).
- Minimum whole packet: 16 bytes. Padding is at least 4 and at most 255 bytes.
- A received `packet_length` above **35000** is a disconnect (RFC 4253 §6.1), checked **before**
  any allocation: this field is attacker-controlled on the first bytes of the connection.
- Padding is random for the transport to be correct, but a **zero-filled padding is not a
  protocol error**; the host tests therefore assert padding *length* rules, never its content.

### Under `chacha20-poly1305@openssh.com`

Two keys, `K_1` (length field) and `K_2` (payload), split from the derived key material. The
4-byte length is encrypted with `K_1` at block counter 0; the payload with `K_2` at counter 1;
the Poly1305 tag covers the encrypted length **and** the encrypted payload, and is verified
**before** the payload is decrypted or its length is trusted.

## The exchange hash H (REQUIRED, RFC 4253 §8, RFC 8731 §3)

```
H = SHA-256( string  V_C || string  V_S ||
             string  I_C || string  I_S ||
             string  K_S ||
             string  Q_C || string  Q_S ||
             mpint   K )
```

Encodings, which are where implementations go wrong:

- `string` is a `uint32` length followed by the bytes, never NUL-terminated.
- `mpint` is two's-complement, big-endian, **minimum length**: leading zero bytes are removed,
  and a leading **0x00 is prepended when the high bit of the first byte is set** so the value
  stays positive. Zero is the empty string.
- `I_C` and `I_S` are the **entire KEXINIT payloads** including the message number, not the
  name-lists alone.
- `K` is the X25519 shared secret **as an integer** (mpint), not as a 32-byte string.
- The session identifier is the first `H` and never changes afterwards, even across rekeys.

An X25519 shared secret of all zeros is a protocol error (RFC 8731 §3): the connection is
dropped, not continued.

## Key derivation (REQUIRED, RFC 4253 §7.2)

Each key is `SHA-256(K || H || X || session_id)` extended, per the RFC, with
`K || H || K_1 || K_2 …` when more bytes are needed. `X` is the single character `A`–`F` for the
six keys. Under an AEAD only the two encryption keys are used, and the IV/MAC slots are still
derived so the transcript matches the RFC.

## Authentication (REQUIRED)

- `none` is **refused**, always, with a partial-success-free `SSH_MSG_USERAUTH_FAILURE` listing
  only `publickey` (RFC 4252 §5.2, §7).
- `password` is not implemented and is not listed.
- `publickey` accepts `ssh-ed25519` keys listed in the image's `/etc/auton/authorized_keys` on
  the FAT32 volume, one per line, in OpenSSH's `ssh-ed25519 <base64> [comment]` form.
- A signature is verified over the exact blob RFC 4252 §7 defines, including the session
  identifier. A key that is present but whose signature does not verify is a failure, and the
  server does not say which of the two it was.

## The channel (REQUIRED)

One `session` channel. `shell` is accepted; `exec` and `subsystem` are refused with
`SSH_MSG_CHANNEL_FAILURE`. The channel's data is the chat REPL's stdin and stdout — the same
`slm_chat_loop()` the serial console drives. Window adjustments are honoured; a `pty-req` is
acknowledged without implementing terminal modes (line mode only, stated so no client is
misled), and no port forwarding, X11 or SFTP is implemented.

## Markers

```
[SSH] listening on 22
[SSH] session opened
```

## Verification

`tests/kernel/run_ssh_test.sh --self-test` runs the host suite against
`tests/kernel/ssh_reference/`, covering what a host can prove: packet framing and its refusals,
name-list negotiation, the `string`/`mpint` encodings, and the exchange-hash input assembled
byte-for-byte, checked against a **real OpenSSH client's** recorded KEXINIT
(`tests/kernel/ssh_fixtures/`). `KERNEL_TREE=<dir>` gates a generated `kernel/services/ssh/`:
exit 2 not generated, exit 1 wrong.

What no host test proves: that a real client completes a session. That is the acceptance step —
`ssh -p 2222 auton@127.0.0.1` reaching `auton>` through QEMU's hostfwd — and it needs the
service implemented in a tree.
