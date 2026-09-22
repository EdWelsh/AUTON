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

---

# Verdict: **GO** (2026-09-22)

Every cell passes. The gate's own runs: `tests/crypto/run_crypto_gate.sh` (criteria b and c);
criteria a and d are judged here, with citations.

| Primitive | Source | (a) vetted | (b) freestanding | (c) vectors | (d) licence |
|---|---|---|---|---|---|
| X25519 | Monocypher 4.0.2 | Cure53 audit (see caveat) | PASS | RFC 7748 §5.2 | PASS |
| Ed25519 | Monocypher 4.0.2 `optional/` | Cure53 audit (see caveat) | PASS | RFC 8032 §7.1 TEST 2, key + signature, and a flipped bit rejected | PASS |
| SHA-512 | Monocypher 4.0.2 `optional/` | Cure53 audit (see caveat) | PASS | NIST `"abc"` | PASS |
| ChaCha20 | Monocypher 4.0.2 (`_ietf`) | Cure53 audit (see caveat) | PASS | RFC 8439 §2.4.2 | PASS |
| Poly1305 | Monocypher 4.0.2 | Cure53 audit (see caveat) | PASS | RFC 8439 §2.5.2 | PASS |
| SHA-256 | BearSSL `hash/sha2small.c` + `codec/{enc,dec}32be.c` | wide deployment, cited | PASS | NIST one-block and two-block | PASS |

**(b), measured, not assumed**: compiled with `x86_64-elf-gcc -ffreestanding -nostdlib
-fno-builtin -O2`, then linked into one relocatable object; the **whole set's** undefined symbols
are exactly `memcpy memset`. Judging per object would have been wrong — one unit calling
another's function is internal. BearSSL's `inner.h` includes `<string.h>`, so the gate supplies a
freestanding stub declaring only what a kernel provides; needing anything more is a compile error.

**(c)**: `tests/crypto/vectors.c`, built with clang under ASan+UBSan: 10 checks, all PASS. Two of
its failures were the harness's own and are worth recording, because they are what vectors are
for: Monocypher's `crypto_chacha20_djb` takes an 8-byte nonce (RFC 8439 needs `_ietf`), and
RFC 8439's `00:00:00:09` nonce belongs to §2.3.2's block-function example, not §2.4.2's.

## Citations

- **Monocypher audit**: Cure53, *Audit-Report Monocypher Crypto Library 06.2020*
  (https://cure53.de/pentest-report_monocypher.pdf), commissioned via the Open Technology Fund.
  No High or Critical findings.
  **Caveat, recorded rather than glossed**: that audit covered **3.1.1**; the source used here is
  **4.0.2**, a later major version with API changes. The audit is evidence about the codebase, not
  about the exact bytes in use. Either pin to an audited release or re-examine the delta before
  anything ships: tracked as a follow-up in the report, not silently accepted.
- **BearSSL deployment**: the TLS stack of the ESP8266 Arduino Core, documented as such
  (https://arduino-esp8266.readthedocs.io/en/latest/esp8266wifi/bearssl-client-secure-class.html).
  BearSSL has **no published independent audit**; criterion (a) is met on the deployment limb,
  and that distinction is deliberate.
- **Licences**: Monocypher is dual BSD-2-Clause / CC0-1.0; BearSSL is MIT. All three are
  `permitted` for `port` in `licences.yaml` with `depends_on_use: false`.

## Rejected candidates, and exactly why

| Candidate for SHA-256 | Outcome |
|---|---|
| Mbed TLS 3.6.2 `library/sha256.c` | Its `mbedtls_platform_zeroize` lives in `platform_util.c`, which needs `free` even with `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS`. **(b) fails** |
| libsodium 1.0.20 `hash_sha256_cp.c` | Compiles, but needs `sodium_memzero` beyond `{memcpy, memset}`, and libsodium's own headers warn that compiling a unit this way is unsupported. **(b) fails** |

## What this does NOT decide

- It does not put SSH in an image. It says the primitives may be **ported** under `third_party/`
  with their licence text, recorded driver-style, and that `ssh.md` may be written.
- It does not permit writing any primitive here. That remains excluded (`STRATEGY.md`), and a
  primitive that later fails its vectors is a CUT, not a rewrite.
- It says nothing about the SSH transport's own correctness. The exchange hash must be proved
  byte-exact against a real OpenSSH session on the host before anything boots (RFC 4253 §8).
