# Report: Factory Pipeline + Gates (F5)

**Plan**: `.claude/PRPs/plans/w3-factory-pipeline.plan.md`
**Source PRD**: `auton-service-kernel-factory.prd.md` — phase 5

```
$ build_service.py dhcp --tree kernels/x86_64
built dhcp: 26 sources, 53,056 bytes
  [ok] spec: valid, resolves, not a stub
  [ok] link closure: 10 absence stub(s)
  [ok] build: linked
  [ok] leakage: clean
```

Byte-identical to F4's hand-walked image.

## Why a pipeline, specifically

F4 found seven defects. **Five were disagreements between steps** — the stub generator
compiling without the build's defines, one source appended twice because two steps each added
it, a stub list maintained separately from the check that reads it.

Those are not bugs in any step. They are bugs in the seam, and they only exist because a human
typed each step's arguments and had to keep them consistent. A pipeline that derives each thing
once cannot reproduce them:

- `STATIC_NET` is one dict, handed to the stub generator and to `make`.
- `KERNEL_CFLAGS` is one list, likewise.
- The source list is built once, de-duplicated, and used for both.
- The stub list is written by the generator and read by the leakage gate — never typed.

## The gates, each proven by violating it

| Injected defect | Caught by | Message |
|---|---|---|
| Spec still carries intent-C's stub marker | **spec** | "still carries the generated-stub marker … fill in the behaviour" |
| `udp` in both requires and excludes | **spec** | "udp in both 'requires' and 'excludes'" |
| `requires: [telepathy, …]` | **spec** | "field 'requires' names unknown capabilities: telepathy" |
| `e1000` removed from requires | **link closure** | "no stub signature for: e1000_init, e1000_poll, e1000_tx" |

The fourth is the one that matters. It **passes the spec gate** — `service_spec.py --validate`
says `OK dhcp.md` — and fails at link closure with the exact symbols named. The gates are
layered, and each catches a class the one before it cannot see. That is the plan's Task 4:
an injected defect failing at a named gate rather than at boot.

Every refusal carries `[gate: <name>]`. A bare "build failed" sends someone reading a
200-line log to work out which step.

### The stub-marker gate

intent-C emits valid front-matter over an empty body. It passes every structural check and is
not implementable. Refusing it is the difference between an agent writing code against a real
spec and against a placeholder — and the placeholder validates, which is what makes it
dangerous.

## Markers are data now

`acceptance_tests.service_marker_patterns(<service>)` reads the `markers` field from the
service spec and escapes it. `[DHCP]` is a literal the kernel prints, not a character class.

A marker written down twice drifts, and the copy the harness reads is the one that stops
matching — which presents as a broken image rather than a stale assertion. A test changes the
spec and asserts the harness follows.

An unknown service raises rather than returning an empty tuple, because an empty marker set
asserts nothing and passes.

## Acceptance

- [x] `build_service.py dhcp` reproduces F4's image from one command, byte-identical
- [x] Defines derived once and shared; no step can disagree with another
- [x] A spec carrying the generated-stub marker is refused
- [x] Leakage is a build gate, using the generated stub list
- [x] A service's markers drive the harness rather than a restatement
- [x] An injected defect fails at a named gate, not at boot — demonstrated four ways
- 13 tests

## Not done

**The marker gate does not run.** `build_service.py` checks the spec, the link closure and
leakage, but does not boot the image and assert its markers. F4 established why: the DHCP
service has never answered a real packet, so four of its five markers cannot appear, and a gate
that always fails would be turned off.

Booting and asserting marker 1 alone would pass while proving almost nothing. The honest state
is that the marker gate is specified, its data source is wired, and it is not enforced until a
client exchange works.

## Follow-on

- The client exchange is now the single thing blocking both F4's last criterion and this gate.
  A second QEMU guest on a socket network is the tractable route; `hostfwd` has been ruled out
  across four configurations.
- `build_service.py` hardcodes `STATIC_NET`. It should come from the manifest once intent-B
  learns to express a network configuration — today no manifest field says "static 10.0.2.15".
- F6 now has a complete path to compare against: one command, four gates, a measured image.
