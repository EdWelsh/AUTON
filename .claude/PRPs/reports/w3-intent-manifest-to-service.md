# Report: Manifest to Service Spec (intent-C)

**Plan**: `.claude/PRPs/plans/w3-intent-manifest-to-service.plan.md`
**Source PRD**: `auton-intent-to-os-compiler.prd.md` — phase C

The intent chain is now connected end to end: a sentence becomes a manifest (B), a manifest
becomes a service spec (C), and the factory already consumes that format (F2).

```
$ intent_service.py "I want to play Doom"
wrote agent/kernel_spec/services/play-doom.md
  service play-doom, entry play_doom_serve, 3 markers
  resolves to 8 subsystems: boot, dev, drivers, hal, mm, pkg, slm, sys
  body is a stub — the front-matter is derived, the prose is not written
```

## The body is a stub, deliberately

The front-matter is *derived* — every field traces to the manifest or the capability index, and
the result validates and resolves. The prose is **empty on purpose**, with a block at the top
saying so.

This is the plan's Task 2 and it is the more important half. `dhcp.md` cites RFC 2131
normatively. A generator that wrote plausible-looking protocol prose would produce a document an
agent implements confidently and wrongly — the phantom-PCI-id failure one layer up, and worse
here, because a spec is treated as authoritative by everything downstream.

A test asserts the body contains no RFC citation, no wire-format term, no state machine. Not
"probably doesn't" — checked.

Every heading `subsystems/*.md` uses is present and empty, so a human fills gaps rather than
inventing a structure. And intent-B's recorded assumptions survive the handoff into an
`## Assumptions carried from the intent` section — an applied default that vanishes between the
manifest and the spec is lost exactly where an implementer would read it.

## Nothing invalid reaches disk

Validation runs against a temporary copy before anything is written. A rejected spec sitting in
`kernel_spec/services/` looks authoritative, and the next reader has no way to tell it was
rejected.

Tested by forcing validation to fail and asserting the directory stays empty — the ordering is
the property, and asserting it any other way would pass even if the write came first.

## Task 3 found a second hand-written bug

Round-tripping the generated DHCP spec against the hand-written `dhcp.md` produced one
difference: the generated spec resolves to 8 subsystems including `slm`; the hand-written one
to 7 without it.

The PRD settles it. `<output>/` contains *"the bootable ISO, an installer, **the scoped model**
and its manifest"*. Every AUTON image ships a manifest-scoped model and a chat terminal — an
image the user cannot ask anything is not what this OS is.

So the generator was right and **both** hand-written service specs were wrong. `dhcp.md` and
`fileserver.md` now require `scoped`, and `dhcp.md` records why.

That is the second defect a round-trip has found in a hand-written artifact — intent-B found
`webserver.json` promising markers its capabilities could not produce. Two for two. Hand-written
files reviewed once by one person are exactly where a generator earns its keep, and the
generator is only trustworthy because the comparison is a required step rather than an
afterthought.

## Acceptance

- [x] A manifest emits a service spec that `service_spec.py` validates and resolves
- [x] A spec failing validation is never written to disk, asserted by forcing the failure
- [x] The generated body is an explicit stub, fabricating no protocol behaviour
- [x] Differences against the hand-written spec resolved in writing — one found, and it was the
      hand-written file that was wrong
- 19 tests

## Follow-on

- A generated spec is not implementable until a human writes the body. That is the honest state
  and the stub says it; what it does not do is stop an agent picking the file up and trying. F5's
  pipeline should refuse to build a service whose spec still carries the stub marker.
- The five intent rules each produce a valid spec, but only `serve-dhcp` has a hand-written
  counterpart to check against. The other four are unverified beyond resolving.
