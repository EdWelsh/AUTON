# Plan: Driver Capability Honesty (V1 + V3)

## Summary

The build advertises driver capabilities it cannot deliver. A manifest requiring `nvme` resolves
to a closed slice, passes every gate in the factory pipeline, and produces an image with **no
storage driver in it**. This makes that a build failure, and makes the failure message name the
device rather than only its id.

## User Story

As someone building an OS image for a machine with an NVMe disk,
I want the build to fail when nothing can drive that disk,
So that I find out at build time rather than when the image boots and cannot read anything.

## Problem → Solution

A required capability with no implementation is reported in a dictionary field nobody reads
→ a required capability with no implementation refuses the build, naming the device.

## Metadata
- **Complexity**: Small
- **Source PRD**: `.claude/PRPs/prds/auton-driver-development.prd.md`
- **PRD Phase**: V1 (truth up the capability index) + V3 (identification from the registry)
- **Estimated Files**: 5 (2 changed, 2 created, 1 test)

### Why these two and not V1–V5

The PRD's dependency chain, checked rather than assumed:

| Phase | Depends on | Eligible? |
|---|---|---|
| V1 | — | **yes** |
| V3 | H2 (landed) | **yes** |
| V2 | D1 — planned in `w6-target-definition-format`, **not built** | no |
| V4 | V2, V3 | no |
| V5 | V2, F5 | no |

V2's input is a target definition, and the format for one does not exist yet. V4 and V5 sit
behind it. Planning them now would produce plans against an interface nobody has written.

---

## UX Design

### Before
```
$ build_service.py storage-image --tree kernels/x86_64
built storage-image: 24 sources, 61,208 bytes
  [ok] spec: valid, resolves, not a stub
  [ok] link closure: 8 absence stub(s)
  [ok] build: linked
  [ok] leakage: clean
                      ... and the image has no NVMe driver.
```

### After
```
$ build_service.py storage-image --tree kernels/x86_64
REFUSED: [gate: capabilities] the spec requires capabilities this tree cannot
  implement:
    nvme  — NVM Express controller (drivers)   no source mapping
  A slice containing them resolves and builds; the image would simply not
  contain the driver. Add a mapping in source_map.yaml, or remove the
  requirement.
```

### Interaction Changes

| Touchpoint | Before | After | Notes |
|---|---|---|---|
| `build_service.py` | 4 gates, none about implementability | 5 gates | Mirrors the existing `[gate: <name>]` convention |
| `build_manifest.py --csrc` | silent | unchanged | `--csrc` is consumed by `make`; the gate belongs in the pipeline |
| Failure message | `unmapped_capabilities: ['nvme']` in a report field | device name from the registry | V3 supplies the name |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/tools/build_service.py` | 87–160 | `GateFailure`, `gate_spec`, `gate_leakage` — the pattern the new gate must match exactly |
| P0 | `agent/tools/build_manifest.py` | 100–145 | `resolve()` already computes `unmapped_capabilities`; the gate consumes it rather than recomputing |
| P0 | `agent/kernel_spec/source_map.yaml` | all | `core_provides` vs `capabilities`; a capability satisfied by the mandatory core is **not** unmapped |
| P1 | `agent/tools/vendor_ingest.py` | 38–70, 95–130 | `Record` shape and `parse_ids_registry` — V3's data source |
| P1 | `agent/tools/vendor_fetch.py` | 40–75 | `Provenance`; every derived fact cites its document |
| P2 | `agent/tests/unit/test_build_service.py` | all | Test class style: one behaviour per test, docstring says *why* |
| P2 | `agent/tools/errata_table.py` | 1–30 | The three-valued-answer precedent: never a bare boolean when "cannot tell" is possible |

## External Documentation

None needed. `pci.ids` is already ingested (21,564 devices, `reports/w2-hardware-ingestion.md`)
and both phases use established internal patterns.

---

## Patterns to Mirror

### GATE_PATTERN
```python
# SOURCE: agent/tools/build_service.py:112-129
def gate_spec(name: str) -> "ServiceSpec":   # noqa: F821
    path = SERVICES / f"{name}.md"
    try:
        spec = load_service(path)
        spec.resolve()
    except ServiceSpecError as exc:
        raise GateFailure(f"[gate: spec] {exc}") from exc
    ...
    return spec
```
Every gate: `[gate: <name>]` prefix, raises `GateFailure`, explains what to do next.

### EXCEPTION_PATTERN
```python
# SOURCE: agent/tools/build_service.py:87-89
class GateFailure(Exception):
    """A gate refused the build. Always names which gate and why — 'build
    failed' sends someone reading a 200-line log to find out which step."""
```
The docstring states the failure mode the class exists to prevent.

### RECORD_PATTERN
```python
# SOURCE: agent/tools/vendor_ingest.py:38-54
@dataclass
class Record:
    """One fact from one document. ..."""
    kind: str                       # device | register | erratum
    key: str                        # the natural key: "8086:100e", an erratum id
    title: str
    vendor: str
    document_id: str
    document_revision: str
    retrieved_at: str
    sha256: str
```
Provenance travels with every derived fact — `document_id`, `document_revision`, `sha256`.

### THREE_STATE_PATTERN
```python
# SOURCE: agent/tools/errata_table.py — Verdict
class Verdict(str, Enum):
    APPLIES = "YES"
    NOT_APPLICABLE = "NO"
    UNKNOWN = "UNKNOWN"
```
When "cannot tell" is possible, it is a distinct value. V3 must not report an unidentifiable
device as unidentified-therefore-absent.

### TEST_STRUCTURE
```python
# SOURCE: agent/tests/unit/test_errata_table.py:122-131
class TestNeverGuess:
    def test_disagreeing_lines_with_an_unresolved_identity_is_unknown(self):
        t = table([], FakeErratum("X2", [
            {"line": "S", "status": "No Fix"}, {"line": "U", "status": "Fixed"}]))

        a = t.applies(Identity("GenuineIntel", 6, 151, 2), t.records[0])

        assert a.verdict is Verdict.UNKNOWN
        assert "false statement" in a.reason
```
Arrange / blank line / act / blank line / assert. Class names state the property.

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `agent/tools/device_registry.py` | CREATE | V3: deterministic id → identity, with provenance |
| `agent/tools/build_service.py` | UPDATE | V1: add `gate_capabilities` before the build |
| `agent/kernel_spec/source_map.yaml` | UPDATE | Comment stating that unmapped means *this tree does not implement it*, which is now enforced |
| `agent/tests/unit/test_device_registry.py` | CREATE | V3 |
| `agent/tests/unit/test_build_service.py` | UPDATE | V1 gate tests |

## NOT Building

- **V2 (decision record format)** — blocked on D1; its input does not exist.
- **V4 (strategy selection)** and **V5 (virtio-net)** — behind V2.
- **Any driver.** This plan makes the absence of one visible; it does not supply one.
- **Marking capabilities unavailable in the spec index.** `subsystems/*.md` describes what a
  subsystem *provides*; `source_map.yaml` describes what a *tree implements*. Conflating them
  would make the spec index tree-specific, and there is one index and many trees.
- **Changing `capability_slice`.** It resolves specs and knows nothing about source maps. The
  gate belongs where the tree is known.

---

## Step-by-Step Tasks

### Task 1: Device identification from the registry (V3)
- **ACTION**: `agent/tools/device_registry.py` — `identify(device_id) -> Identification`.
- **IMPLEMENT**: Load the ingested `pci-sig/pci-ids` records via `vendor_ingest.ingest`, index by
  `key`, return the title plus the provenance of the document it came from.
- **MIRROR**: `RECORD_PATTERN` for the return shape; `THREE_STATE_PATTERN` for the outcome.
- **IMPORTS**: `from vendor_ingest import ingest`, `from vendor_fetch import Provenance`.
- **GOTCHA**: The registry lives in `.cache/vendor/`, which is gitignored and may be absent.
  A missing registry must yield **`UNAVAILABLE`**, distinct from `UNKNOWN` (registry present,
  device genuinely not listed). Collapsing them would report every device as unidentifiable on a
  fresh checkout, and a gate built on that would refuse every build.
- **VALIDATE**: `identify("8086:100e")` returns the Intel 82540EM title with document
  provenance; `identify("ffff:ffff")` returns `UNKNOWN`; with `.cache` removed, returns
  `UNAVAILABLE`.

### Task 2: The capabilities gate (V1)
- **ACTION**: `gate_capabilities(spec, tree)` in `build_service.py`, called **before** the stub
  generator and the build.
- **IMPLEMENT**: Call `resolve(spec.requires, spec.excludes, tree)`, read
  `report["unmapped_capabilities"]`, intersect with `spec.requires` — a capability that is
  unmapped but only reached transitively is a weaker case and must not fail the build.
  Raise `GateFailure` listing each offending capability with its owning subsystem.
- **MIRROR**: `GATE_PATTERN` exactly — `[gate: capabilities]` prefix, and a message saying what
  to do next.
- **IMPORTS**: already present (`resolve`, `GateFailure`).
- **GOTCHA**: `source_map.yaml` has `core_provides` — capabilities satisfied by the mandatory
  core carry no explicit mapping and are **not** unmapped. `resolve()` already honours this
  (`build_manifest.py:130`); the gate must not re-derive the list and get it wrong.
- **VALIDATE**: a spec requiring `nvme` is refused naming it; the shipped `dhcp` and
  `fileserver` specs still build.

### Task 3: Name the device, not just the capability
- **ACTION**: Where a capability maps to a device id, the refusal includes the identity from
  Task 1.
- **IMPLEMENT**: Extend the gate message: `nvme — NVM Express controller (drivers)`.
- **MIRROR**: `GATE_PATTERN`'s habit of explaining rather than reporting.
- **GOTCHA**: If the registry is `UNAVAILABLE`, the gate must still fire — it just cannot add the
  name. An unidentifiable device is not a reason to allow an unimplementable build.
- **VALIDATE**: with `.cache` removed, the gate still refuses `nvme`, without the friendly name.

### Task 4: Record what unmapped means
- **ACTION**: A comment block at the top of `source_map.yaml`.
- **IMPLEMENT**: State that an absent mapping means *this tree does not implement this
  capability*, that it is now a build failure when required directly, and that 27 capabilities
  are currently unmapped because the seed tree never implemented `ipc`, `sched`, `fs` or `pkg`.
- **GOTCHA**: Do not "fix" the 27 by inventing mappings to directories that do not exist. That is
  the defect, not the cure — `framebuffer` → `kernel/drivers/fb/**` already maps to a directory
  that has never existed, and it resolves without error.
- **VALIDATE**: the comment names the count and the reason.

### Task 5: Tests
- **ACTION**: `test_device_registry.py` (new) and gate tests in `test_build_service.py`.
- **MIRROR**: `TEST_STRUCTURE`.
- **IMPLEMENT**: See Testing Strategy below.
- **VALIDATE**: `pytest -q` green; the gate test fails if the gate is removed.

---

## Testing Strategy

### Unit Tests

| Test | Input | Expected | Edge case? |
|---|---|---|---|
| A known device identifies | `8086:100e` | Intel 82540EM title + provenance | no |
| An absent device is UNKNOWN | `ffff:ffff` | `UNKNOWN`, not an empty string | yes |
| A missing registry is UNAVAILABLE | `.cache` removed | `UNAVAILABLE` ≠ `UNKNOWN` | yes |
| Identification cites its document | `8086:100e` | `document_revision` and `sha256` present | no |
| A directly required unmapped capability refuses | spec requires `nvme` | `GateFailure`, names `nvme` | no |
| A transitively unmapped capability does not refuse | requires `terminal` only | builds | yes |
| A core-provided capability is not flagged | requires `serial` | builds | yes |
| The shipped specs still build | `dhcp`, `fileserver` | build | no |
| The gate fires without a registry | `.cache` removed, requires `nvme` | still refuses | yes |
| The refusal says what to do | any | mentions `source_map.yaml` | no |

### Edge Cases Checklist
- [ ] Registry absent (fresh checkout — the common case)
- [ ] Registry present, device not listed
- [ ] Capability satisfied by `core_provides`
- [ ] Capability unmapped but only reached transitively
- [ ] Capability mapped to a directory that does not exist (`framebuffer`) — **currently passes;
      out of scope here, recorded as a follow-on**
- [ ] A tree with no sources at all

---

## Validation Commands

### Static Analysis
```bash
.venv/bin/python -c "import ast;[ast.parse(open(f).read()) for f in \
  ['agent/tools/device_registry.py','agent/tools/build_service.py']]"
```
EXPECT: no output

### Unit Tests
```bash
cd agent && ../.venv/bin/python -m pytest tests/unit/test_device_registry.py \
  tests/unit/test_build_service.py -q
```
EXPECT: all pass

### The defect, demonstrated fixed
```bash
.venv/bin/python agent/tools/device_registry.py --identify 8086:100e
# EXPECT: Intel Corporation 82540EM Gigabit Ethernet Controller, with provenance

.venv/bin/python agent/tools/build_service.py <a spec requiring nvme> --tree <tree>
# EXPECT: REFUSED: [gate: capabilities] ... nvme ... no source mapping
```

### Full Suite
```bash
cd agent && ../.venv/bin/python -m pytest tests/unit/ -q -m "not slow"
.venv/bin/python -m pytest SLM/tests/ -q
```
EXPECT: no regressions (1094 passed / 26 skipped at time of writing)

### Manual Validation
- [ ] `build_service.py dhcp --tree <tree>` still builds and still reports 4 prior gates
- [ ] Removing `.cache/vendor` does not break any build that previously worked
- [ ] The refusal message is legible without reading source

---

## Acceptance Criteria
- [ ] A spec requiring a directly-unmapped capability is refused, naming it
- [ ] The refusal names the device where the registry can identify it
- [ ] A missing registry yields `UNAVAILABLE`, distinct from `UNKNOWN`, and does not disable the gate
- [ ] Capabilities satisfied by `core_provides` are never flagged
- [ ] Transitively-unmapped capabilities do not fail the build
- [ ] `dhcp` and `fileserver` still build unchanged
- [ ] `source_map.yaml` records what an absent mapping means
- [ ] No regressions in the full suite

## Completion Checklist
- [ ] Gate follows `[gate: <name>]` and raises `GateFailure`
- [ ] Derived facts carry provenance
- [ ] Three-state outcome where "cannot tell" is possible
- [ ] Tests state the property in the class name
- [ ] No mapping invented for a capability nothing implements
- [ ] Self-contained — no codebase searching needed to implement

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The gate refuses builds that previously worked | **M** | High | Only *directly required* capabilities fail; `dhcp` and `fileserver` are regression fixtures |
| A fresh checkout has no registry and every build fails | **H** | High | `UNAVAILABLE` is distinct and never disables the gate, but also never blocks on identification. Tested with `.cache` removed |
| Someone "fixes" the 27 by inventing mappings | **M** | High | Task 4 states this explicitly; `framebuffer` is the cautionary example already in the file |
| The gate duplicates `resolve()`'s logic and drifts | **M** | Medium | The gate consumes `report["unmapped_capabilities"]` and never recomputes it |
| `framebuffer`-style mappings to non-existent directories still pass | **H** | Medium | Out of scope and recorded. A mapping that points nowhere is a different defect from no mapping, and needs the tree to exist to detect |

## Notes

**The PRD understated this.** It said `ahci` and `nvme` have no source mapping. The measured
number is **27 capabilities across 9 subsystems** — including `vfs`, `initramfs`, `preemptive`,
`channels` and `module-asset`.

Most of those are correct information, not defects: `source_map.yaml` is per-tree, and the seed
tree never implemented `ipc`, `sched`, `fs` or `pkg`. The defect is that nothing acts on it.
`resolve()` computes the list, `main()` prints a warning to stderr, and `build_service.py` — the
actual pipeline — never reads it.

So V1 is not "mark six capabilities unavailable". It is **make the existing, correct information
load-bearing**, which is a smaller change and a more durable one.

**One related defect deliberately left open.** `framebuffer` maps to `kernel/drivers/fb/**` and
`virtio-blk` to `kernel/drivers/blk/**` — directories that have never existed. Those resolve
without error today, because a glob matching nothing is not an error. That is a *third* state
between mapped and unmapped, it needs a tree on disk to detect, and folding it into this plan
would make the gate depend on tree contents rather than on the map. Recorded as a follow-on.
