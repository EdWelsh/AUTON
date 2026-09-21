# Service Spec Format

A **service** is one purpose an image can be built for. `kernel_spec/subsystems/` says what the
kernel *can* do; a service spec says what one image *is for*, by composing capabilities those
subsystems provide and adding the protocol behaviour that is specific to it.

This is the factory's input format and the target intent-C compiles a sentence into. A spec
here must be complete enough that an agent can implement the service from it without seeing
any other service.

## Shape

Front-matter, then prose in the voice of `subsystems/*.md`.

```yaml
---
service: dhcp
requires: [netif, ipv4, udp, allocator, klog]
excludes: [tcp, fs, preemptive]
entry: dhcp_serve
markers:
  - "[DHCP] listening on :67"
  - "[DHCP] offer 10.0.2.100 to 52:54:00:12:34:56"
  - "[DHCP] lease bound"
assets: []
---
```

## Why each field exists

| Field | Why it is here |
|---|---|
| `service` | The image's identity. One service per image — the unikernel premise the factory rests on. Must match the filename. |
| `requires` | Capability names from the subsystem index (`subsystems/*.md` front-matter). Makes the subsystem slice *computable* rather than asserted. A service spec never names a capability the index does not define. |
| `excludes` | The load-bearing field. Without it "minimal" is unfalsifiable; with it, leakage is a build failure rather than an opinion. A service that excludes `fs` and ships a filesystem is a bug you can test for. |
| `entry` | The single serve loop. A service image has one — no process model, no scheduler, no second thing to run. Naming it makes the generated `main` trivial and makes "one purpose per image" checkable. |
| `markers` | Ordered serial lines the image must emit. The spine asserts on these, so an image is verifiable without bespoke test code per service. Mirrors `SERIAL_MARKER_SETS` in `acceptance_tests.py`. |
| `assets` | Files handed in as Multiboot2 modules — a WAD, a docroot, a lease database. Named here so the build can require them and so nothing copyrighted is ever committed. |

Nothing else. A field is added when a second service genuinely cannot be expressed without it,
not in anticipation.

## Rules

1. **Do not restate a subsystem spec.** `net.md` already specifies the UDP wire format. A
   service spec `requires: [udp]` and describes only what *this service* does with it.
2. **`requires` names capabilities, not subsystems**, wherever a capability exists. `udp` is
   precise; `net` drags in ARP, ICMP and DNS that the service may not want.
3. **Cite protocols normatively.** "RFC 2131 §4.3.1" is implementable; a paraphrase is a
   second source of truth that will drift.
4. **Every marker must be emitted on a successful run**, in the order listed. A marker that
   only sometimes appears makes the spine flaky, which is worse than no assertion.
5. **A spec must resolve.** `service_spec.py --resolve` computes the closed subsystem slice
   and refuses a spec whose `requires` transitively need something its `excludes` forbid.

## Validating

```bash
python agent/tools/service_spec.py --validate agent/kernel_spec/services/dhcp.md
python agent/tools/service_spec.py --resolve  agent/kernel_spec/services/dhcp.md
```

## Services

| Spec | Shape it exercises | Status |
|---|---|---|
| [dhcp.md](dhcp.md) | UDP, stateless request/response, no storage | format example; F4 implements |
| [fileserver.md](fileserver.md) | TCP, stateful, needs storage | proves the format generalises |
| [play-doom.md](play-doom.md) | no network, no storage; framebuffer, input, a boot-module asset | emitted by intent-C, body written in w11; engine licence undecided |

The two are structurally different on purpose. A format that expresses only the service it was
written alongside has not been tested.
