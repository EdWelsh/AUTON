# Report: Dependency Audit + Manifest Build (F1)

**Plan**: `.claude/PRPs/plans/w2-factory-dependency-audit.plan.md`
**Source PRD**: `auton-service-kernel-factory.prd.md` — phase 1

## Task 1: the audit

`agent/tools/kernel_graph.py`'s output compared against the intent-A front-matter:

| subsystem | files | lines | declared | real | undeclared |
|---|---|---|---|---|---|
| boot | 2 | 170 | `arch` | arch, dev, drivers, mm, net, slm | **dev, drivers, mm, net, slm** |
| slm | 5 | 1365 | mm, sys | arch, mm, net, sys | **net** |
| lib | 5 | 300 | (mapped to mm) | drivers | **drivers** |
| server | 3 | 105 | (no spec) | drivers, mm, net | all |
| arch | 5 | 396 | (no spec) | lib | **lib** |
| net | 7 | 990 | dev, drivers, mm | dev, mm | — |
| dev, drivers, sys | 1 each | 48–78 | several | ~none | tree stubs |

Depended on by real edges: `mm` ×5, `drivers` ×4, **`net` ×3**, `dev` ×2, `arch` ×2.

`net` being depended on by three subsystems — including `boot` — is the entanglement. A
network stack that `boot` calls into cannot be excluded from an image by omitting its sources.

The second finding is that **`lib` is the real mandatory core**, not `mm`. `kprintf`, `kstr`,
`kmath` and `string` are called by everything including `arch`, and `lib` has no spec of its
own; the graph extractor maps it to `mm.md` because `phys.c` (the bump allocator) lives there.
Splitting utility code from the allocator is a prerequisite for F3's real PMM.

### Mandatory core

Defined from what the audit measured, not from intuition: `kernel/arch/**`, `kernel/boot/**`,
`kernel/lib/{kprintf,kstr,kmath,string}.c`, `kernel/sys/console.c`, `kernel/drivers/arch/**`.

The console is core because every image emits `[BOOT]`, `[MM]` and `[DEV]` markers before
anything else exists. An image that cannot report why it failed is worse than one that fails.

## Task 2: manifest-resolved source list

`agent/tools/build_manifest.py` + `agent/kernel_spec/source_map.yaml`.

The mapping is data rather than a path convention because it is genuinely not one-to-one:
`net` is `kernel/net/` *and* the e1000 driver; `allocator` is one file inside `kernel/lib/`;
`terminal` is `kernel/slm/chat.c`.

**The full manifest reproduces the glob byte-identically — 29 sources.** That check ran before
any scoping was used, because a refactor that changes the general image while claiming to add
scoping is two changes wearing one commit.

| manifest | sources | excluded |
|---|---|---|
| everything (`--all`) | 29 | 0 |
| dhcp service | 20 | 9 |
| framebuffer + terminal, `--excludes net` | 16 | 13 |

Two mapping bugs the resolver exposed in its own data, both fixed: `sockets` pulled `tcp.c`
into a UDP-only image, and moving `serial` into the core's provides dropped `console.c`
because the core patterns did not cover it.

## Task 3: the entanglement, measured

A reduced slice does not link. Building the no-network slice gives **10 undefined references**:

```
net_bringup  net_dns  net_gw  net_ip  net_is_up
roles_dispatch  slm_backend_name  slm_driver_for_pci  slm_init  slm_process_text
```

Five from `kernel_main`'s fixed call order, five from the chat loop calling `net_ip()` and
friends directly. Omitting a source does not omit its caller, which is precisely why
`excludes` is unenforceable today.

This is now the **third independent route to the same conclusion**:

1. `graph.json` records `boot -> net` as a real edge (`w1-spec-capability-index.md`).
2. A Doom-scoped image answered `what is my ip` from the compiled-in rule engine
   (`e2e-intent-scoped-corpus.md`).
3. A no-network slice fails to link, naming the ten symbols (here).

The fix is specified rather than hand-written, because `kernels/` is generated output and the
repo's premise is that agents write it. `boot.md` gained a **Generated Init Sequence
(REQUIRED)** section: `kernel_main` walks a table emitted from the slice and contains no
subsystem name; order comes from the same `depends_on` front-matter the slice uses; the chat
loop reads facts from a provider table rather than calling `net_ip()`; and `roles.c`'s
capability table is generated, so a role outside the slice is **absent** rather than a null
pointer — a null entry is a crash where an absent one is an honest refusal.

## Task 4: proving absence in the binary

`tests/kernel/run_leakage_test.sh` + `leakage_check.py`. Attribution is **by object file, not
by symbol name**: each excluded source is compiled and its defined symbols recorded, then the
image is checked for those. A name list would be a second source of truth that drifts, and
would miss anything static or renamed.

Demonstrated in both directions against real artifacts:

| image | excludes | result |
|---|---|---|
| full seed kernel (200,536 bytes, 184 symbols) | `net` | **68 leaked symbols**, exit 1 |
| mandatory core, partial link (44 symbols) | `net` | none, exit 0 |

Exit codes distinguish the three states that matter: 1 = leaked, 2 = nothing to check (no
image, or nothing maps), 0 = clean. An unbuilt image must not read as a clean one.

Three further refusals, each because the alternative is a false pass: an empty symbol dump is
refused rather than reported clean; an exclude naming nothing is an error, since an exclude
that excludes nothing is worse than none; and a source that could not be compiled for
attribution makes the run **INCONCLUSIVE**, not passing — its absence was never checked.

## A toolchain trap, confirmed

The first build attempt failed with `unsupported option '-mno-mmx' for target
'arm64-apple-darwin'`. `scripts/lib/toolchain.sh` documents exactly this: GNU make predefines
`CC`, so the Makefile's `CC ?= x86_64-elf-gcc` never fires and a bare `make` picks up Apple
clang. The comment was right and is now confirmed by an independent encounter.

## Acceptance

- [x] Declared vs real coupling recorded per subsystem, each discrepancy resolved
- [x] A mandatory core defined and justified from measurement
- [x] The full manifest reproduces today's source list byte-identically (29 sources)
- [ ] **A no-network slice links without `net_bringup`** — it does not, and the 10 undefined
      references are the measurement. The fix is specified in `boot.md`; implementing it means
      generating kernel code, which is F6's job, not a hand edit here
- [x] `nm` proves omitted subsystems contribute no symbols, enforced by a spine-owned test,
      demonstrated in both directions

## Follow-on

- The init-sequence generation is the gate on intent-E. Until it lands, `excludes` is enforced
  on the source list and violated by the linker.
- Splitting `lib` (utility) from `mm` (`phys.c`) should happen with F3's real PMM; they are
  the same refactor.
- `source_map.yaml` covers the seed tree's layout. A generated tree will differ, and the map
  is data precisely so that is a config change rather than a code change.
