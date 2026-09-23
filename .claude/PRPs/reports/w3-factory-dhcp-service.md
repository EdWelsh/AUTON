# Report: Service #1 — DHCP Server, Human-Authored (F4)

**Plan**: `.claude/PRPs/plans/w3-factory-dhcp-service.plan.md`
**Source PRD**: `auton-service-kernel-factory.prd.md` — phase 4

Human-authored on purpose. This phase proves the *factory*, and asking agents to generate a
service the process has never produced manually conflates a bad spec with a bad generation.
The cost recorded here is F6's control.

## The image

| | general kernel | DHCP service image |
|---|---|---|
| size | 200,536 bytes | **53,056 bytes** |
| sources | 29 | 23 |
| global symbols | 179 | 96 |

**73.5% smaller** — the PRD asked for ≥40%.

It boots, reaches `[DHCP] listening on :67`, and the static-IP path works: `[NET] static IP
10.0.2.15` with no DISCOVER sent, because a DHCP server cannot DHCP for itself.

`nm` confirms no excluded capability leaks, with `tcp_input` correctly distinguished as a
generated absence stub rather than the real implementation.

## The tests found a spec-conformance gap

24 host tests, under ASan and UBSan, exercising `dhcp_handle` with no NIC — which is exactly
why `dhcp.md` split it from `dhcp_serve`. The cases that matter most are the ones a live client
never produces: a malformed option length, an exhausted pool, a REQUEST for an address nobody
offered.

One test failed for a real reason. `dhcp.md` says an option length overrunning the frame is a
drop. My `find_option` stops at the option it is looking for, so a malformed option *after* the
message type was never seen — a DISCOVER with corrupt trailing options was served normally. The
parse was memory-safe either way; the behaviour did not match the spec. Fixed by validating the
whole option block before dispatch, and the test now covers a bad length on both sides of the
message-type option.

## Building found a spec bug

`dhcp.md` never required a NIC driver. It validated, resolved to a closed slice, and passed
every check that reads a spec — then the link failed on `e1000_init`.

A DHCP server serves over a network interface. The spec is corrected and says how it was found:
**a gap invisible to every check that inspects the spec rather than the artifact.**

## The F1 wall, and what got through it

The plan expected this, and it arrived: a reduced slice does not link. After including the NIC
and the static-IP define, 10 undefined references remained — `roles.c` registering
`http_server_run` by direct function pointer, `slm.c` calling the neural backend
unconditionally, `ipv4.c` dispatching to `tcp_input`.

`boot.md`'s Generated Init Sequence specifies the eventual fix. Rather than hand-editing
generated kernel code — which is the thing this repo exists to avoid — the smaller step is a
**generator**: `agent/tools/gen_absent.py` emits a stub for every symbol the slice references
but does not define, and each stub **reports absence** rather than pretending to succeed.

That distinction is the whole point. A stub returning success turns a missing capability into
wrong behaviour at runtime; one that says `[ABSENT] http_server_run: not in this image` turns
the same thing into a legible message.

The generator refuses to guess. Given a symbol with no known signature it stops and says so,
because inventing one produces a link that succeeds and a call that corrupts the stack.

It also emits the service's `entry` as a strong `service_main()`, replacing a weak default in
`kernel_main` that runs the chat loop. So the entry point is data from the service spec rather
than a hand edit.

### Three bugs in my own tooling, found by using it

- **The generator scanned its own output.** `absent.c` lands in `kernel/boot/`, which the
  mandatory core matches, so a second run saw its own stubs as definitions, found nothing
  missing, and wrote an empty file over a working one. Now excluded from its own scan.
- **It ignored assembly.** `isr.S` defines `isr_default` and the IRQ stubs; scanning only `.c`
  reported them missing and the generator offered to stub over real interrupt handlers.
- **It compiled without the build's defines**, leaving the DHCP client path live so `dhcp_run`
  looked absent. A stub generated from a different configuration than the one that ships is
  worse than none.

### Two bugs in the leakage test, found the same way

- **Static symbols caused false positives.** `seg.0` is a file-local static in `netif.c` that
  happens to share a name with one in `tcp.c`, so the check reported TCP leaking into an image
  that does not contain it. Attribution is now global symbols only — a static cannot leak
  across a link.
- **It could not tell a stub from an implementation.** `tcp_input` in the image is 1 byte, a
  bare `ret`. The generator now writes a sidecar list of what it stubbed, and the check reports
  those separately. The list is generated rather than hand-maintained, because a drifted
  exemption list forgives a real leak.

## What is not demonstrated

**A real client did not obtain a lease.** The five markers `dhcp.md` declares are emitted by
code paths the host tests exercise and print, but only the first appears on a booted image.

Tried, in order: the guest at 10.0.2.1 and at 10.0.2.15; `hostfwd` with an implicit and an
explicit guest address; and announcing the guest to QEMU's NAT by ARPing the gateway at startup
— which the DHCP path already does and the static path did not, and which is a correct fix
regardless. Packets sent to the forwarded port never reach the guest's UDP handler.

The general image's DHCP *client* works under the same SLIRP, so receive works in principle.
What fails is inbound-initiated UDP to a guest that only ever ARPs. Proving the cause needs
packet capture inside the guest, which is a larger diagnostic than this phase should carry.

Recorded rather than worked around: an image whose service has never answered a real packet has
not been proven, whatever its markers say.

## Acceptance

- [x] `dhcp_handle` passes host tests for every case `dhcp.md` lists, including malformed options
- [x] A static-IP path exists and the image never sends a DISCOVER
- [~] **`auton-dhcp.iso` boots and emits the five markers in order** — it boots and emits the
      first. Markers 2–5 require a client exchange that QEMU's user networking did not deliver
- [x] Image size stated: 53,056 vs 200,536 bytes, 73.5% smaller
- [x] The cost of human authorship recorded below, for F6 to be compared against

## The control for F6

| | |
|---|---|
| Spec | `services/dhcp.md`, 175 lines, written in F2 |
| Implementation | `server.c` 320 lines, `serve.c` 52 lines, `dhcp.h` 60 lines |
| Tests | `dhcp_test.c` 200 lines, 24 cases |
| Defects caught by tests | 1 spec-conformance gap (option-block validation) |
| Defects caught by building | 1 spec bug (no NIC required) |
| Defects caught in tooling | 5 (3 in the generator, 2 in the leakage check) |
| Not caught by anything | the client exchange — no test covers the QEMU network path |

The last row is the useful one for F6. Seven defects were found by three different checks, and
the one thing none of them covered is the one thing that remains unproven.

## The implementation is preserved as structure, not text

`kernels/` is gitignored — it is generated output — so the hand-written service source is not
committed. The repo's own convention answers what to keep: *"a hand-written tree is a
reference, not a product, and what is worth keeping from a reference is its structure, not its
text"* (`kernel_spec/reference/README.md`).

`kernel_graph.py` now captures it: the `services` subsystem, 2 files, 401 lines, 21 symbols,
with `dhcp_handle`, `dhcp_expire`, `dhcp_server_init` and the rest recorded with real
signatures.

One thing fell out of that worth noting. The graph reports `services` really depending on
`arch`, `lib` and `net` — which is **exactly what its spec declares**. Every subsystem in the
retired tree had undeclared real edges, `boot` with five of them. A service written against the
capability index came out with declared and real dependencies in agreement, first time. That is
weak evidence, being one service, but it is the first evidence either way.

## Follow-on

- F5 turns this walked path into `auton build-service <name>`. Every step here was a hand-typed
  `make` with an explicit `CSRC`; that is what the pipeline replaces.
- The client exchange needs either a second QEMU guest on a socket network or a tap interface.
  Worth doing under F5, where the pipeline can own the harness.
- `gen_absent.py` is a bridge, not the destination. `boot.md`'s generated init sequence and role
  table remain the real fix, and F6 is where they get written by the loop rather than by hand.
