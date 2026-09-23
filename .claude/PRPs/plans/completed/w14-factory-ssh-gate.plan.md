# Plan: Service #5, SSH, Gated on Vetted Freestanding Crypto (F10)

## Summary
The PRD pre-commits the outcome space: *"Either an interactive SSH session into the AUTON chat,
or a written decision not to hand-roll crypto. Both outcomes are acceptable; hand-rolled crypto
is not"* (`auton-service-kernel-factory.prd.md:380-386, 425`). This plan runs the **gate** as a
bounded spike with stated pass criteria and records the decision. Only on a pass does it
continue to a minimal SSH server whose channel is the chat terminal.

## User Story
As an operator, I want either a real SSH session into an AUTON image or a documented reason
there is none, so that `roles.c` never advertises an SSH server built on invented crypto.

## Problem → Solution
`roles.c:31` says "needs crypto (key exchange, ciphers) and a PTY" → a decision record with
evidence (compiles freestanding, passes published vectors, audit status, licence), and then
either `services/ssh.md` + a build, or a `roles.c` note citing the cut.

## Metadata
- **Complexity**: Medium for the gate; Large if it passes
- **Source PRD**: `auton-service-kernel-factory.prd.md` phase 10
- **Estimated Files**: gate: 4; build: ~8 more
- **Depends on**: F5 (landed). The build half also needs `w13-factory-f6-rerun`'s protocol decision

---

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `.claude/PRPs/prds/auton-service-kernel-factory.prd.md` | 108, 141-143, 380-386, 425 | the non-negotiables |
| P0 | `agent/kernel_spec/drivers/licences.yaml` | all | licence obligations are a table, decided by it (GPL → human) |
| P0 | `agent/hardware/vendors.yaml` | structure | where a vetted source gets inventoried |
| P1 | `agent/kernel_spec/drivers/STRATEGY.md` | all | reuse > port > synthesize applied to crypto: synthesize is excluded outright |

## External Documentation
| Topic | Source | Key Takeaway |
|---|---|---|
| SSH transport | RFC 4253; RFC 8731 (curve25519-sha256); RFC 8709 (ssh-ed25519); OpenSSH PROTOCOL.chacha20poly1305 | the minimum modern suite: kex `curve25519-sha256`, host key `ssh-ed25519`, cipher `chacha20-poly1305@openssh.com` |
| Monocypher | monocypher.org, 4.x; audited by Cure53 (2020) | X25519, EdDSA (SHA-512 variant in `optional/`), ChaCha20, Poly1305, no libc, no allocation; CC0/BSD-2 |
| SHA-256 (needed by the kex) | not in Monocypher | the candidate must come from a vetted source (e.g. BearSSL's `hash/sha2small.c`, MIT) or the gate fails on this item |
| Test vectors | RFC 7748 §5.2, RFC 8032 §7.1, RFC 8439 §2.8.2, NIST CAVP SHA-256 | the pass criteria, run on the host |

GOTCHA: "vetted" means an independent audit or wide deployment, stated with a citation. Popularity
alone is not evidence, and neither is an inventoried URL.

## Patterns to Mirror
### DECISION_RECORD
// SOURCE: agent/kernel_spec/drivers/ps2-keyboard.md (w11): a decision taken in writing, the evidence listed, what it does NOT change stated.
### LICENCE_TABLE
// SOURCE: agent/kernel_spec/drivers/licences.yaml: `reuse`/`port` per licence; `depends_on_use` routes to a human.

## Files to Change (gate)
| File | Action | Justification |
|---|---|---|
| `agent/hardware/vendors.yaml` | UPDATE | inventory the candidate sources (Monocypher, the SHA-256 source) with licence and audit citation |
| `tests/crypto/` (`run_crypto_gate.sh`, vector files) | CREATE | compile each primitive with `x86_64-elf-gcc -ffreestanding -nostdlib -fno-builtin` and a stub `string.h`, and run the vectors on the host with clang + ASan |
| `agent/kernel_spec/decisions/ssh-crypto.md` | CREATE | the decision record: GO or CUT, with evidence |
| `.claude/PRPs/reports/w14-factory-ssh-gate-report.md` | CREATE | |

## Files to Change (only on GO)
| File | Action |
|---|---|
| `agent/kernel_spec/services/ssh.md` | CREATE: RFC 4253 transport, one kex/hostkey/cipher each, `none` auth refused, `publickey` only (RFC 4252 §7), the channel bound to the chat terminal, no PTY semantics beyond line mode |
| `tests/kernel/ssh_test.c` + reference | CREATE: packet framing, the kex hash transcript against a recorded OpenSSH session |
| `third_party/` handling | port per `licences.yaml`; the source recorded in a driver-style record |

## NOT Building
- Any crypto primitive written here. A primitive failing the gate is a CUT, not a rewrite.
- Password auth, SFTP, port forwarding, multiple ciphers, RSA.

## Step-by-Step Tasks
### Task 1: Pass criteria, written first
- **ACTION**: In the decision record, before any compile: each of X25519, Ed25519, SHA-256, SHA-512, ChaCha20, Poly1305 must (a) come from a source with a citable audit or deployment record, (b) compile freestanding with zero undefined symbols beyond `memcpy`/`memset`, (c) pass its RFC/NIST vectors, and (d) carry a licence `licences.yaml` marks `permitted` without `depends_on_use`.
- **VALIDATE**: the criteria are committed before Task 2's first run (git history shows the order).

### Task 2: Spike
- **ACTION**: `run_crypto_gate.sh` per primitive, printing PASS/FAIL per criterion.
- **GOTCHA**: `-fno-builtin` matters. GCC turns loops into `memset` calls, and a "freestanding" build that silently needs libc passes on the host and fails at kernel link.
- **VALIDATE**: a table of 6 primitives × 4 criteria.

### Task 3: Decide and record
- **ACTION**: GO if every cell passes; otherwise CUT, naming the failing cell. On CUT, write the `roles.c` note text for F12: *"cut: no vetted freestanding <primitive> (see kernel_spec/decisions/ssh-crypto.md)"*.

### Task 4 (GO only): `ssh.md` + host tests
- **GOTCHA**: the exchange hash must be byte-exact (RFC 4253 §8). Record a real OpenSSH client's KEXINIT and prove the transcript hash against it on the host before anything boots.

### Task 5 (GO only): Build and connect
- **VALIDATE**: `ssh -o HostKeyAlgorithms=ssh-ed25519 -p 2222 auton@127.0.0.1` via hostfwd reaches `auton>`; a line typed there is answered by the SLM.

## Validation Commands
```bash
tests/crypto/run_crypto_gate.sh
# GO only:
tests/kernel/run_ssh_test.sh --self-test && .venv/bin/python agent/tools/build_service.py ssh --tree <ws> --iso
```

## Acceptance Criteria
- [ ] Criteria written before the spike
- [ ] A decision record: GO or CUT, cell by cell
- [ ] GO: an interactive session reaches `auton>`. CUT: the `roles.c` note text is drafted for F12
- [ ] No primitive written in this repo

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| SHA-256 has no vetted freestanding source | M | CUT | an acceptable outcome, per the PRD |
| Licence mixing (MIT + CC0 + source-available) | M | M | `licences.yaml` decides; a human for anything `depends_on_use` |
