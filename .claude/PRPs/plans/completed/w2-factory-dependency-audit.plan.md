# Plan: Dependency Audit + Manifest Build (F1)

**Source PRD**: `.claude/PRPs/prds/auton-service-kernel-factory.prd.md` — phase 1
**Complexity**: Medium — a small refactor, not a Makefile edit
**Unblocks**: F4 (first service), F5 (pipeline), intent-E (leakage enforcement)

## Summary

The build compiles every `.c` under `kernel/`. A manifest that says an image excludes `net`
changes nothing about what is linked, so `excludes` is unenforceable at the point it matters
most — the binary.

This replaces the glob with a manifest-resolved source list and adds a symbol assertion
proving omitted subsystems are genuinely absent. That assertion is the deliverable: without it,
"minimal" is a claim about intent rather than about the artifact.

## Evidence

- `kernels/x86_64/Makefile:19` — `CSRC := $(shell find kernel -name '*.c')`. Every source,
  unconditionally.
- `kernels/x86_64/kernel/boot/kernel_main.c:23-89` — a **fixed call order** hardcoding
  `pci_scan`, `sysinfo_init`, `slm_init`, `irq_enable`, `net_bringup`, `slm_chat_loop`. A
  no-network image cannot be produced by omitting a source file; `kernel_main` would not link.
- `kernels/x86_64/kernel/slm/roles.c:21-23` — `caps[]` registers `http_server_run` by direct
  function pointer, so the role table pulls in the HTTP server whatever the manifest says.
- Corroborated twice already, independently:
  - `agent/kernel_spec/reference/x86_64/graph.json` records `boot -> dev, drivers, net, slm`
    (`.claude/PRPs/reports/w1-spec-capability-index.md`).
  - A Doom-scoped image still answered `what is my ip` from the compiled-in rule engine
    (`.claude/PRPs/reports/e2e-intent-scoped-corpus.md`, *The image is not actually scoped*).
- `agent/tools/capability_slice.py` already computes the closed subsystem set. The input to
  this plan exists; nothing consumes it.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Slice computation | `agent/tools/capability_slice.py` `capability_slice()` | Already returns subsystems + capabilities; do not reimplement |
| Service resolution | `agent/tools/service_spec.py` `ServiceSpec.resolve()` | The manifest -> slice path a build should call |
| Spine-owned verification | `tests/kernel/run_mm_test.sh` | `KERNEL_TREE` parameter; exit 2 = not generated, 1 = wrong |
| Honest marker | `w1-kernel-pmm-spec` `[MM]` change | A marker that any value satisfies asserts nothing |

## Tasks

### Task 1: Audit the real coupling
- **Action**: For each subsystem directory, record what it includes, what it calls outside
  itself, and what registers into a table elsewhere. Compare against the `depends_on`
  front-matter added by intent-A. The graph extractor already exists
  (`agent/tools/kernel_graph.py`) — use it rather than grepping.
- **Output**: a table of declared-vs-real per subsystem, and a proposed **mandatory core**
  (the set no image can omit) versus optional leaves.
- **Validate**: every real edge is either in the front-matter or recorded as a finding.

### Task 2: Manifest-resolved source list
- **Action**: `agent/tools/build_manifest.py` takes a service spec or a capability manifest,
  calls `capability_slice`, and emits the `.c`/`.S` list. The Makefile reads that instead of
  globbing.
- **Gotcha**: a subsystem maps to more than one directory (`net` is `kernel/net/` *and* the
  `e1000` driver under `kernel/drivers/`). The mapping is data, not a path convention, and
  belongs next to the front-matter.
- **Validate**: the full manifest reproduces today's source list exactly — byte-identical
  `CSRC`. A refactor that changes the general image while claiming to add scoping is two
  changes wearing one commit.

### Task 3: Break the fixed call order
- **Action**: `kernel_main` calls an init sequence generated from the slice, not a hardcoded
  list. Smallest viable form: a generated `kernel/boot/init_sequence.c` listing the init
  functions of subsystems in the slice, in dependency order.
- **Expect entanglement.** `roles.c`'s direct function pointers are the hard case; a role whose
  implementation is not in the slice must be absent from the table, not a null pointer.
- **Validate**: a slice without `net` produces a `kernel_main` that links, with no reference to
  `net_bringup`.

### Task 4: Prove absence in the binary
- **Action**: `tests/kernel/run_leakage_test.sh` — `nm` the built ELF and assert no symbol
  from an excluded subsystem is present. Symbol-to-subsystem mapping comes from the same data
  as Task 2.
- **Why this is the deliverable**: every other check in this plan is about inputs. This is the
  only one that inspects the artifact, and intent-E's enforcement is built on it.
- **Validate**: a general image and a reduced image build from the same tree; `nm` proves the
  reduced one is missing the omitted symbols, and the test fails if they reappear.

## Validation

```bash
python agent/tools/build_manifest.py --service dhcp --tree kernels/x86_64
make -C kernels/x86_64 MANIFEST=dhcp
KERNEL_TREE=kernels/x86_64 tests/kernel/run_leakage_test.sh --excludes net,fs
nm kernels/x86_64/build/kernel.elf | grep -c net_bringup   # expect 0
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `kernel_main`'s fixed order resists decomposition | **H** | Expected and stated in the PRD. Generated init sequence, mandatory core kept deliberately large at first |
| `roles.c` function pointers drag in everything | **H** | Table entries generated from the slice; a role outside it is absent, not null |
| The refactor changes the general image | **M** | Task 2 requires byte-identical `CSRC` for the full manifest before any scoping is used |
| Symbol assertion passes because the symbol was inlined | **M** | Assert on the subsystem's *file* contributing no symbols, not on one name |

## Acceptance
- [ ] Declared vs real coupling recorded per subsystem, with each discrepancy resolved
- [ ] A mandatory core is defined and justified
- [ ] The full manifest reproduces today's source list byte-identically
- [ ] A no-network slice links without `net_bringup`
- [ ] `nm` proves omitted subsystems contribute no symbols, enforced by a spine-owned test
