# Decision: crypto for an SSH service (factory F12 gate)

**Status: criteria written, spike not yet run.** This section is committed *before* the spike, so
the criteria cannot be adjusted to fit what the spike happens to produce. The verdict is appended
below, with the evidence, cell by cell.

The factory PRD pre-commits the outcome space: *either an interactive SSH session into the AUTON
chat, or a written decision not to hand-roll crypto. Both outcomes are acceptable; hand-rolled
crypto is not.* `STRATEGY.md`'s ladder applies with its top rung removed: **reuse > port;
synthesize is excluded for cryptographic primitives.** A primitive that fails this gate is a CUT,
never a rewrite.

## The suite, and why these primitives

The minimum modern SSH transport: kex `curve25519-sha256` (RFC 8731), host key `ssh-ed25519`
(RFC 8709), cipher `chacha20-poly1305@openssh.com` (OpenSSH PROTOCOL.chacha20poly1305), framing
per RFC 4253. That set needs exactly six primitives: **X25519, Ed25519, SHA-256, SHA-512,
ChaCha20, Poly1305**. (SHA-512 because Ed25519 is defined on it; SHA-256 because the kex hash is.)

## Pass criteria (all four, for every one of the six)

| # | Criterion | How it is judged |
|---|---|---|
| a | **Vetted source** | an independent audit or a wide-deployment record, cited. Popularity alone is not evidence, and neither is an inventoried URL |
| b | **Freestanding** | compiles with `x86_64-elf-gcc -ffreestanding -nostdlib -fno-builtin -O2`, and the object's undefined symbols are a subset of `{memcpy, memset}`. `-fno-builtin` matters: GCC turns loops into `memset` calls, so a "freestanding" build can silently need libc and fail only at kernel link |
| c | **Published vectors** | passes its own RFC or NIST vectors, run on the host under ASan/UBSan: X25519 RFC 7748 §5.2, Ed25519 RFC 8032 §7.1, ChaCha20 RFC 8439 §2.4.2, Poly1305 RFC 8439 §2.5.2, SHA-256/512 NIST CAVP (the standard one/two-block examples) |
| d | **Licence** | `licences.yaml` marks it `permitted` for the act used (`reuse` or `port`) with `depends_on_use: false` |

**GO** only if every cell passes. Otherwise **CUT**, naming the failing cell, and F12's `roles.c`
note becomes: `cut: no vetted freestanding <primitive> (see kernel_spec/decisions/ssh-crypto.md)`.

Nothing here writes a primitive. On GO, the sources are ported under `third_party/` with their
licence text, recorded in a driver-style record, and `ssh.md` follows.

<!-- verdict appended by the spike; nothing above this line changes -->
