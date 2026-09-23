# Report: Spec Capability Index (intent-A)

**Plan**: `.claude/PRPs/plans/w1-spec-capability-index.plan.md`
**Source PRD**: `auton-intent-to-os-compiler.prd.md` — phase A

## What was added

All 11 subsystem specs and 4 arch specs now carry capability front-matter:

```yaml
---
subsystem: net
provides: [netif, ethernet, arp, ipv4, icmp, udp, tcp, dhcp-client, dns,
           http-client, http-server, sockets]
depends_on: [mm, dev, drivers]
optional: [tcp, dhcp-client, dns, http-client, http-server]
---
```

69 capabilities, no capability owned by two subsystems, every `optional` also in
`provides`, every `depends_on` resolving. Names come from each spec's own Interface
headings and from the two manifests that exist, not from an invented taxonomy.

`agent/tools/capability_slice.py` computes the closed slice, and refuses an impossible one:

```
$ capability_slice.py --requires framebuffer,input,terminal --excludes net
subsystems (6): boot, dev, drivers, hal, mm, sys

$ capability_slice.py --requires tcp --excludes mm
REFUSED: 'tcp' requires 'mm', which is excluded.
  path: net -> mm
```

The two real manifests slice differently and correctly: Doom to 8 subsystems / 24
capabilities with no `net`, `sched`, `fs` or `ipc`; webserver to 8 / 30 including `net`.

Parsing is deliberately hand-rolled rather than a YAML dependency — the block is three list
fields, and agents read these specs as plain text (`base_agent.py`), so the format has to stay
trivial. `---` blocks are inert to a text reader.

## Task 2: declared against observed

`reference/x86_64/graph.json` records the edges the retired tree actually had. `lib` is that
tree's utility module and its spec pointer is `mm.md`, so it is read as `mm` below.

| subsystem | declared | observed | resolution |
|---|---|---|---|
| boot | `arch` | `arch, dev, drivers, mm, net, slm` | **code was wrong** — see below |
| slm | `mm, sys` | `arch, mm, net, sys` | **code was wrong** — see below |
| dev | `boot, mm` | (none) | tree stub, 78 lines. Declaration is the contract |
| drivers | `arch, dev, mm` | (none) | tree stub, 58 lines. Declaration is the contract |
| net | `dev, drivers, mm` | `dev, mm` | tree talked to the NIC through `dev` with no driver layer. Spec is the contract |
| sys | `drivers, mm` | `drivers` | tree's sys was minimal and allocated nothing |
| arch | — | `mm` (`lib`) | **layering inversion in the tree**; arch sits beneath mm |
| mm, sched, ipc, fs, pkg | declared | not in the tree | never built. Expected — the tree implemented a fraction of the spec |
| server | — | `drivers, mm, net` | no spec of its own; it is net's `http-server` capability |

Two of these are findings rather than bookkeeping.

**`boot` depends on everything.** The retired tree's boot calls into `dev`, `drivers`, `net`
and `slm` directly, and `boot.md`'s prose says so: *"Boot calls into: mm, sched, ipc, dev,
slm, drivers"*. If that were a dependency, every image would contain `net` and `excludes: net`
could never be satisfied — the whole intent design would be unbuildable.

It is not a dependency. It is an init-time call into whatever is present, hard-coded in a tree
that only ever built one configuration. The declaration `depends_on: [arch]` is the contract:
**a generated boot path initialises the subsystems in its slice and no others.** The observed
edges are the coupling that makes the retired tree unsliceable, which is a reason it was
retired.

**`slm` reaches into `net`.** The retired SLM answered network questions by calling `net_ip()`
directly. This is the same defect the scoped-corpus work found from the other end: a Doom
image still answers `what is my ip` because the kernel's rule engine calls into the network
stack (`e2e-intent-scoped-corpus.md`, *The image is not actually scoped*). Two independent
routes to one conclusion.

Declared `depends_on: [mm, sys]` is the contract. The SLM must receive facts through a
provider interface populated from the slice, not by calling subsystems that may not be in the
image. Recorded for intent-C.

## Acceptance

- [x] 15 specs carry `provides` / `depends_on` / `optional` front-matter
- [x] No capability provided by two subsystems (enforced at load by `build_owner_index`)
- [x] Declarations reconciled against `graph.json`, every discrepancy resolved above
- [x] A slice is provably closed; a requires/excludes conflict is refused **with the path**
- [x] Unknown capabilities raise — never an empty slice, which would look like a correctly
      minimal image
- [x] 20 tests; agent spec-reading unaffected (front-matter is inert text)

## Follow-on

- `boot`'s init sequence is generated per slice, not fixed. That claim is untested until
  intent-E's leakage check runs against a generated image.
- The `slm -> net` coupling needs a fact-provider interface before any image can honestly
  claim `excludes: net`.
- `optional` is doing real work — `capability_slice(["ipv4"])` correctly ships no DHCP client,
  DNS resolver or HTTP server. That is the mechanism image size will come from.
