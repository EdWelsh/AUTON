# Report: The SSH Crypto Gate, and the Service It Permits (F12)

**Plan**: `plans/completed/w14-factory-ssh-gate.plan.md` · **Commits**: `a5c5c28` (criteria),
`c309116` (gate + verdict), `181cc21` (spec + suite) · **Record**:
`agent/kernel_spec/decisions/ssh-crypto.md`

## Verdict: GO

Criteria were committed **before** the spike (`a5c5c28`, git history shows the order), and a test
asserts they still stand above the verdict, unedited.

| Primitive | Source | (a) vetted | (b) freestanding | (c) vectors | (d) licence |
|---|---|---|---|---|---|
| X25519, Ed25519, SHA-512, ChaCha20, Poly1305 | Monocypher 4.0.2 | Cure53 2020 (caveat) | PASS | RFC 7748/8032/8439 | BSD-2 / CC0 |
| SHA-256 | BearSSL `sha2small.c` + `codec/{enc,dec}32be.c` | ESP8266 Arduino Core | PASS | NIST 1- and 2-block | MIT |

**Linked as one set, the undefined symbols are exactly `memcpy memset`.** Judging per object
would have been wrong: one unit calling another's function is internal. Ten vectors pass under
ASan+UBSan.

Two caveats are in the record rather than glossed: Cure53 audited Monocypher **3.1.1**, not the
4.0.2 in use; and BearSSL has **no** published audit — it meets (a) on the deployment limb only.

**Rejected for SHA-256, each naming the symbol**: Mbed TLS 3.6.2 (`platform_util.c` needs `free`
even with `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS`), libsodium 1.0.20 (`sodium_memzero`, and its own
headers warn that compiling a unit this way is unsupported).

## Two harness bugs the vectors caught, worth recording

Both were mine, and both are exactly what published vectors are for:
1. `crypto_chacha20_djb` takes an **8-byte** nonce; RFC 8439 needs `_ietf`.
2. RFC 8439's `00:00:00:09` nonce belongs to §2.3.2's block-function example, not §2.4.2's
   encryption vector. A "fix" that changed the nonce made the failure worse, and an independent
   Python implementation settled which side was wrong.

## What GO permitted, and what was built

`agent/kernel_spec/services/ssh.md` (`status: specified`, validates) and a 28-check host suite,
`tests/kernel/run_ssh_test.sh`, covering what a host can prove:

- the binary packet protocol: block multiples, minimum 16 bytes, padding ≥ 4, and the 35000
  refusal **checked before anything is sized from the length field**
- name-list negotiation against a **real OpenSSH 10.3 client's recorded KEXINIT** (captured
  locally into `tests/kernel/ssh_fixtures/`), including that a prefix must not match
- `mpint`: leading-zero stripping, the 0x00 prepended when the high bit is set, zero as empty
- the **exchange-hash input byte for byte** against a fixture built independently in Python from
  RFC 4253 §8 and RFC 8731 §3

8 of 8 injected bugs caught (no mpint pad, kept leading zeros, K as a string, unchecked length,
unchecked padding, prefix match, padding below minimum, Q_C/Q_S swapped). A tree without the
service exits 2.

## What is NOT done, and who it waits for

- **No implementation.** `kernel/services/ssh/` is what a capable model (or a person) writes
  against this spec; the suite and the gate are ready for it.
- **No primitive is in this repo**, and a test checks the harness for one. The sources are
  fetched into the gitignored cache by `tests/crypto/fetch_sources.sh`; porting them under
  `third_party/` with their licence text is part of implementing, not of this gate.
- **The audit-version caveat** should be settled before anything ships: either pin Monocypher to
  an audited release or examine the 3.1.1 → 4.0.2 delta.
- The acceptance step (`ssh -p 2222 auton@127.0.0.1` reaching `auton>`) needs the implementation.
