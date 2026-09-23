# Plan: Spec Capability Index (intent-A)

**Source PRD**: `.claude/PRPs/prds/auton-intent-to-os-compiler.prd.md` — phase A
**Complexity**: Small — spec work, no agents required
**Unblocks**: intent-B (manifest), intent-C (spec handoff), factory manifest resolution

## Summary

The PRD's whole design rests on slicing the 11 subsystem specs down to what an intent needs.
Nothing in those specs declares what a subsystem *provides* or *depends on*, so a slice cannot
be computed, let alone proved closed under dependency.

This adds machine-readable front-matter to each subsystem spec and a function that computes a
closed slice from a capability set. It is the cheapest structural prerequisite in the set and
nothing downstream works without it.

## Evidence

- `agent/kernel_spec/subsystems/` — 11 files: `boot, mm, sched, ipc, dev, drivers, fs, net,
  pkg, sys, slm`. None carries structured capability metadata.
- Dependency information exists but only **empirically**:
  `agent/kernel_spec/reference/x86_64/graph.json` records real subsystem edges from the
  retired tree — `boot → arch, drivers, lib, net, slm`; `server → drivers, lib, net`;
  `slm → lib, net`. That is observed coupling, not declared contract.
- `agent/kernel_spec/arch/hal.md` already decomposes by category (Boot, CPU, MMU, Context
  Switch, Timer, I/O, Device Discovery) — the shape to mirror.
- The intent PRD's `excludes` field is unenforceable without this: you cannot prove a slice
  omits `net` if nothing says which sections provide it.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Spec section shape | `subsystems/slm.md` | `## Overview / Data Structures / Interface / Behavior / Files / Dependencies / Acceptance Criteria` — a `Dependencies` heading already exists as prose |
| HAL decomposition | `arch/hal.md:11-180` | Numbered categories with an explicit C interface each |
| Observed edges | `reference/x86_64/graph.json` | `subsystems[].depends_on` — use to **validate** declarations, not to replace them |
| Marker sets | `acceptance_tests.py` `SERIAL_MARKER_SETS` | Named, ordered sets consumed by shell harnesses — the precedent for machine-readable spec metadata |

## Files to Change

| File | Action | Why |
|---|---|---|
| `agent/kernel_spec/subsystems/*.md` (11) | UPDATE | `provides` / `depends_on` / `optional` front-matter |
| `agent/kernel_spec/arch/*.md` (4) | UPDATE | Same, for arch and HAL sections |
| `agent/tools/capability_slice.py` | CREATE | Compute a closed slice; refuse an open one |
| `agent/tests/unit/test_capability_slice.py` | CREATE | Closure, cycles, and unknown capabilities |

## Tasks

### Task 1: Declare capabilities per subsystem
- **Action**: YAML front-matter on each subsystem spec:
  ```yaml
  ---
  subsystem: net
  provides: [ipv4, arp, tcp, udp, dhcp-client, netif]
  depends_on: [mm, dev, drivers]
  optional: [dhcp-client]
  ---
  ```
  Granularity is per-capability, not per-file: an intent may need `ipv4` without `tcp`.
- **Mirror**: the existing prose `Dependencies` headings — reconcile with them, and where
  declaration and prose disagree, the prose is the bug.
- **Validate**: every subsystem declares at least one capability; no capability is declared by
  two subsystems.

### Task 2: Cross-check declarations against observed reality
- **Action**: Compare declared `depends_on` against `graph.json`'s measured edges from the
  retired tree. A declared dependency the code never had, or a real edge nobody declared, is a
  finding about the spec.
- **Why**: the graph is the only empirical check available, and it is exactly what a reference
  is for.
- **Validate**: discrepancies listed and each resolved as "spec wrong", "code was wrong", or
  "intentional — the declaration is the contract".

### Task 3: Closed-slice computation
- **Action**: `capability_slice(requires, excludes)` returns the transitive subsystem set, and
  **refuses** when a required capability transitively depends on an excluded one — reporting
  the path. That conflict is the interesting output: it tells an operator their intent is
  self-contradictory before anything is generated.
- **Validate**: `requires=[framebuffer]` yields no `net`; `requires=[tcp], excludes=[mm]`
  refuses and names the path.

### Task 4: Tests
- **Action**: Closure correctness, a cycle raising rather than looping, an unknown capability
  rejected loudly, and the conflict case above.
- **Validate**: suite green; an unknown capability never silently yields an empty slice.

## Validation

```bash
python agent/tools/capability_slice.py --requires framebuffer,input,slm --excludes net
python agent/tools/capability_slice.py --requires tcp --excludes mm     # must refuse, with the path
cd agent && python -m pytest tests/unit/test_capability_slice.py -q
python -c "import yaml,glob; [yaml.safe_load(open(f).read().split('---')[1]) for f in glob.glob('agent/kernel_spec/subsystems/*.md')]"
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Capability granularity chosen wrong | **M** | Start from what the intent corpus actually needs (I1 Doom, I2 host-repo) rather than inventing a taxonomy |
| Declared and observed dependencies disagree everywhere | **M** | That is Task 2's output and it is valuable. The retired tree implemented a fraction of the spec, so absent edges are expected |
| Front-matter breaks a spec reader | **L** | `base_agent.py` reads specs as text; `---` blocks are inert. Verify one agent read after the change |
| A slice looks closed but omits something the code needs | **M** | Only generation proves it. The leakage check (intent-E) is the counterpart — this plan produces the claim, that one tests it |

## Acceptance
- [ ] All 11 subsystem specs and 4 arch specs carry `provides` / `depends_on` front-matter
- [ ] No capability is provided by two subsystems
- [ ] Declarations reconciled against `graph.json`, with each discrepancy resolved in writing
- [ ] A slice is provably closed, and a requires/excludes conflict is refused with the path
- [ ] Unknown capabilities are rejected loudly, never as an empty slice
