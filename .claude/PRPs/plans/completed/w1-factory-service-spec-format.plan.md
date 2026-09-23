# Plan: Service Spec Format (F2)

**Source PRD**: `.claude/PRPs/prds/auton-service-kernel-factory.prd.md` — phase 2
**Complexity**: Small — a format definition plus one worked example
**Unblocks**: intent-C (the handoff from a sentence to a spec), F4 (first service), F5 (pipeline)

## Summary

The factory's input format does not exist. `agent/kernel_spec/services/` is absent, so there
is nothing for intent-C to emit into and nothing for F4 to author against. This defines the
format — subsystems, feature flags, entry point, serial markers, required patterns — and
writes one real service spec as the worked example.

Deliberately a *format* plan, not a service plan: F4 builds the first service against it.
Defining the format while simultaneously implementing a service would conflate "the format is
wrong" with "this service is wrong".

## Evidence

- `ls agent/kernel_spec/services` → does not exist.
- 11 subsystem specs exist and are the shape to mirror (`subsystems/*.md`, 11,242 lines).
- `kernel/slm/roles.c` in the retired tree advertised **7 `CAP_WORKING` against 16
  `CAP_ROADMAP`** — the roadmap rows are the candidate service list.
- The intent PRD's phase C is explicitly blocked on this format (`C … depends on B, **F2**`).
- `reference/x86_64/graph.json` records what a working service looked like: the `server`
  subsystem was 3 files, 105 lines, 5 functions, depending on `drivers, lib, net`. A service
  is small, which is the premise the factory rests on.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Spec document shape | `subsystems/net.md` | Overview, Data Structures, Interface, Behavior, Files, Dependencies, Acceptance Criteria |
| Capability declaration | intent-A front-matter (`provides`/`depends_on`) | The same vocabulary — a service spec *consumes* capabilities the subsystem specs provide |
| Marker sets | `acceptance_tests.py` `SERIAL_MARKER_SETS` | Named, ordered, single-sourced; shell harnesses read them rather than restating |
| Honest capability status | `roles.c` `CAP_WORKING` / `CAP_ROADMAP` + note | A service that cannot be built says what it needs |
| Existing service shape | `graph.json` → `server` subsystem | 5 functions over 105 lines; one serve loop |

## Files to Change

| File | Action | Why |
|---|---|---|
| `agent/kernel_spec/services/README.md` | CREATE | The format, and why each field exists |
| `agent/kernel_spec/services/dhcp.md` | CREATE | The worked example — F4's input |
| `agent/tools/service_spec.py` | CREATE | Parse, validate, resolve against the capability index |
| `agent/tests/unit/test_service_spec.py` | CREATE | Validation and resolution |

## Tasks

### Task 1: Define the format
- **Action**: Front-matter plus prose. Minimum viable fields:
  ```yaml
  ---
  service: dhcp
  requires: [ipv4, udp, netif, mm, sys]
  excludes: [tcp, http, fs]
  entry: dhcp_serve          # the one serve loop
  markers:
    - "[DHCP] listening on :67"
    - "[DHCP] lease offered"
  assets: []
  ---
  ```
  Prose carries the protocol behaviour agents implement against, in the subsystem specs' voice.
- **Why these fields**: `requires`/`excludes` make the slice computable and leakage testable;
  `entry` names the single loop the unikernel model implies; `markers` feed the spine's
  assertions so an image is verifiable without bespoke test code.
- **Validate**: the format is expressible for two structurally different services — DHCP
  (UDP, stateless) and a file server (TCP, needs storage) — without new fields.

### Task 2: Write the DHCP service spec
- **Action**: One real spec, complete enough that F4 can be authored from it with no
  additional information. Cite the protocol normatively (RFC 2131) rather than paraphrasing.
- **Mirror**: `subsystems/net.md`'s level of detail — it specifies wire formats and state
  machines, which is the right depth.
- **Why DHCP**: the factory PRD chose it as the cheapest first service, and the retired tree
  already had a DHCP **client**, so the protocol is half-documented in the reference graph.
- **Validate**: a reader who has not seen the retired tree could implement it.

### Task 3: Parse and resolve
- **Action**: `service_spec.py` validates front-matter, resolves `requires` against intent-A's
  capability index, computes the closed subsystem slice, and **refuses** a spec whose
  `requires` and `excludes` conflict.
- **Dependency**: intent-A. If that has not landed, the resolver stubs the index and the test
  is marked pending rather than faked.
- **Validate**: the DHCP spec resolves to a subsystem set that excludes `tcp` and `fs`.

### Task 4: Tests
- **Action**: A malformed spec is rejected with the field named; an unknown capability is
  rejected; a conflicting requires/excludes is refused with the path; the DHCP spec resolves.
- **Validate**: suite green; no spec error is silent.

## Validation

```bash
python agent/tools/service_spec.py --validate agent/kernel_spec/services/dhcp.md
python agent/tools/service_spec.py --resolve  agent/kernel_spec/services/dhcp.md   # subsystem set, no tcp/fs
cd agent && python -m pytest tests/unit/test_service_spec.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| The format is under-specified and F4 has to invent | **H** | Task 1's two-service test, and Task 2's "implementable by a stranger" bar. Expect one revision after F4 — that is the format earning its keep |
| Over-specified, and every service needs bespoke fields | **M** | Start with the minimum above; add a field only when a second service genuinely needs it |
| Duplicates the subsystem specs | **M** | A service spec composes capabilities and adds protocol behaviour. It must not restate what `net.md` already says |
| Blocked on intent-A | **M** | Stub the index; mark the resolution test pending rather than asserting against a fake |

## Acceptance
- [ ] The format is documented with a rationale per field
- [ ] It expresses two structurally different services without new fields
- [ ] `dhcp.md` is complete enough to implement from, citing RFC 2131
- [ ] A spec resolves to a closed subsystem slice, and a requires/excludes conflict is refused
- [ ] Malformed specs and unknown capabilities are rejected with the offending field named
