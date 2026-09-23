# Report: Service Spec Format (F2)

**Plan**: `.claude/PRPs/plans/w1-factory-service-spec-format.plan.md`
**Source PRD**: `auton-service-kernel-factory.prd.md` — phase 2

## What exists now

`agent/kernel_spec/services/` — absent before — contains the format, two service specs, a
parser/resolver and 24 tests.

The format is six fields and nothing else:

| Field | Why |
|---|---|
| `service` | The image's identity; must match the filename, because that is how the factory addresses it |
| `requires` | Capability names from the intent-A index — makes the slice *computable* rather than asserted |
| `excludes` | Load-bearing: without it "minimal" is unfalsifiable, with it leakage is a build failure |
| `entry` | The single serve loop. One per image is the unikernel premise, and naming it makes that checkable |
| `markers` | Ordered serial lines; the spine asserts on these, so no bespoke test code per service |
| `assets` | Multiboot2 modules supplied at build time, so nothing copyrighted is ever committed |

## The format was tested, not just written

The plan's real bar for Task 1 was that the format express two structurally different services
**without new fields**. `fileserver.md` was written second against exactly that bar:

| | dhcp | fileserver |
|---|---|---|
| Transport | UDP, datagram | TCP, connection-oriented |
| State | lease table, no connection state | per-connection state machine |
| Storage | none (`excludes: fs`) | read-only CPIO (`requires: vfs, initramfs`) |
| Assets | none | `docroot.cpio` |
| Subsystems resolved | 7 | 8 |

No field was added. One test asserts that directly (`test_neither_service_needed_a_field_the_other_lacks`).

The sharper result is the file server's `requires: [vfs, initramfs]` alongside
`excludes: [writable, ext2]` — **four capabilities from one subsystem, two in and two out.**
A per-subsystem index could not express that, and it is the first concrete evidence the
per-capability granularity chosen in intent-A was right rather than merely finer.

## Resolution

```
$ service_spec.py --all
OK  dhcp         entry=dhcp_serve           7 subsystems, 5 markers
OK  fileserver   entry=fileserver_serve     8 subsystems, 3 markers
```

dhcp resolves with no `fs` subsystem, no `tcp` and no `writable`. fileserver resolves with
`fs` and `tcp` present and `writable`/`ext2` absent. Both exclusions verified in both
directions.

A contradictory spec is refused with the path:

```
requires: [tcp], excludes: [mm]
  -> INVALID: widget.md: 'tcp' requires 'mm', which is excluded.
       path: net -> mm
```

## What is rejected, and why each

Every failure names the offending field — "invalid spec" would send an author reading the
whole file.

- a missing field, by name
- `service` disagreeing with the filename — a build would otherwise act on the wrong service
- empty `requires`
- empty `markers` — without them the image cannot be verified and the spine has nothing to
  assert, so a spec that ships none is not finished
- a scalar where a list belongs
- a capability absent from the index — otherwise `requires` is decoration that still validates
- the same capability in both `requires` and `excludes`

## Notes on the two specs

`dhcp.md` cites RFC 2131/2132 normatively rather than paraphrasing, specifies the lease table
as a fixed array (a growable pool would put the allocator on the packet path, and a server
that can fail to answer because it is out of memory is worse than one that says "no addresses
left"), and splits `dhcp_handle` from `dhcp_serve` so packet handling is testable without a
NIC — the property a serve loop otherwise destroys.

`fileserver.md` specifies path resolution as the security boundary in five numbered steps,
including decoding exactly once (`%252e%252e` is how a second pass becomes `..`), rejecting
`..` on segment boundaries after decoding rather than by substring, and answering `404` rather
than `403` for anything rejected, since a distinguishable error tells a prober which files
exist.

## Acceptance

- [x] The format is documented with a rationale per field
- [x] It expresses two structurally different services without new fields
- [x] `dhcp.md` is implementable from, citing RFC 2131
- [x] Specs resolve to a closed slice; conflicts refused with the path
- [x] Malformed specs and unknown capabilities rejected with the field named

## Follow-on

- F4 implements DHCP from `dhcp.md`. Expect one format revision then — that is the format
  earning its keep, and the plan anticipated it.
- `markers` are declared but nothing consumes them yet. The spine should read them from here
  rather than restating, the way `SERIAL_MARKER_SETS` already works.
- Neither spec has been built, so "the image contains no TCP" is a claim, not a measurement.
  intent-E's leakage check is the counterpart.
