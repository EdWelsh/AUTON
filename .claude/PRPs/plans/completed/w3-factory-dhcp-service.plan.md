# Plan: Service #1 — DHCP Server, Human-Authored (F4)

**Source PRD**: `auton-service-kernel-factory.prd.md` — phase 4
**Complexity**: Medium — freestanding C against a spec that already exists
**Depends on**: F2 (`dhcp.md`, landed), F1 (manifest resolution, landed)
**Unblocks**: F5 (pipeline), F6 (the agent-authored comparison this is the control for)

## Summary

`dhcp.md` was written to be implementable by a stranger. This implements it, by hand, to prove
the *factory machinery* works before asking agents to drive it. Asking agents to generate a
service the process has never produced manually conflates two failure modes: a bad spec and a
bad generation.

The measurement F6 needs is the cost of this: files, lines, and how many defects the validators
caught.

## Evidence

- `agent/kernel_spec/services/dhcp.md` — 175 lines, full wire behaviour, RFC 2131 cited
  normatively, `dhcp_handle` deliberately split from `dhcp_serve` so packets are testable
  without a NIC.
- `kernels/x86_64/kernel/net/dhcp.c` — the DHCP **client** already exists. The wire format,
  option encoding and the UDP path are therefore already solved in this tree.
- `agent/tools/build_manifest.py --service dhcp` resolves to 20 sources.
- `.claude/PRPs/reports/w2-factory-dependency-audit.md` — a reduced slice does **not** link
  today: 10 undefined references from `kernel_main` and the chat loop. This plan hits that wall
  and must either route around it or fix it.

## Tasks

### Task 1: Static-IP path
- **Action**: A DHCP server cannot DHCP for itself. `net_bringup` currently always runs the
  client; add a static configuration path selected by the manifest.
- **Validate**: the image comes up with a fixed address and never sends a DISCOVER.

### Task 2: The server
- **Action**: `dhcp_server_init`, `dhcp_handle`, `dhcp_expire`, `dhcp_serve` exactly as
  `dhcp.md` specifies. Fixed-size lease table; no allocator on the packet path.
- **Gotcha**: the option-length parser is the classic hole. `dhcp.md` says a length overrunning
  the frame is a drop; implement that before the happy path, not after.
- **Validate**: host tests for DISCOVER→OFFER, REQUEST→ACK, NAK, expiry, and the malformed
  cases, via `dhcp_handle` with no NIC.

### Task 3: Boot it
- **Action**: Build `auton-dhcp.iso` from the manifest-resolved source list.
- **Expect** the F1 link wall. Either generate the init sequence (specified in `boot.md`) or
  record precisely what blocks it.
- **Validate**: the image boots and emits all five markers from `dhcp.md` in order.

### Task 4: Measure
- **Action**: Record image size against the general kernel, source count, and every defect the
  validators caught. This is F6's control.
- **Validate**: size delta stated; the ≥40% target from the PRD confirmed or missed with a number.

## Acceptance
- [ ] `dhcp_handle` passes host tests for every case `dhcp.md` lists, including malformed options
- [ ] A static-IP path exists and the image never sends a DISCOVER
- [ ] `auton-dhcp.iso` boots and emits the five markers in order
- [ ] Image size stated against the general kernel
- [ ] The cost of human authorship recorded, for F6 to be compared against
