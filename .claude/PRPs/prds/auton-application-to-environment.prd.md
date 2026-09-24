# AUTON: Application to Environment

**Status**: draft, 2026-09-24
**Layer**: a second front end for the compiler. The manifest pipeline beneath it already
exists — read [`auton-intent-to-os-compiler.prd.md`](./completed/auton-intent-to-os-compiler.prd.md) first.
**Relationship to [`auton-completion.prd.md`](./auton-completion.prd.md)**: that PRD finishes
what is already defined — twelve generation runs, three decisions, four acquisitions. This one
adds scope it does not contain. Neither blocks the other, and they compete only for attention.

> **Repo intent check.** `README.md` — *"We don't write the kernel. The agents do."* Nothing
> here changes that. This PRD does not generate a kernel and does not ask an agent to write
> one; it derives what an **already-built application** needs, and emits the manifest the
> existing compiler already consumes.

## Problem Statement

You build software on a Mac, or Windows, or whatever is in front of you. Then you say: *now
make it run on this server.* Between those two sentences sits CPU architecture, OS version,
kernel, drivers, runtimes, libraries, networking, containers, orchestration — and a developer
is expected to hold all of it.

AUTON can already answer half of that question. It can read a machine and say what drivers it
needs, with provenance. What it cannot do is look at an application and say what the
application needs.

The front end today knows five sentences:

```
$ intent_manifest.py "containerize my Django app and run it on this server"
DECLINED: I do not know how to build an OS for '...'
  Known intents: play-doom; host-repo; serve-dhcp; serve-files; identify-hardware
```

All five are services AUTON generates itself. There is no ELF inspection, no linked-library
resolution, no runtime detection anywhere in the tree. The input is a sentence matched against
a table — not an artifact.

The cost of not solving it: the compiler can only ever target software AUTON wrote. Every
application that already exists — which is all of the interesting ones — is out of reach.

## Evidence this is the right shape

Each row was checked by running the thing, 2026-09-24.

| Fact | Where |
|---|---|
| The machine half works: `lspci` + `/proc/cpuinfo` → a validated target definition, every fact `source: probed` | `agent/tools/probe_ingest.py`, `target_spec.py --validate` |
| Hardware joins to a driver decision with provenance: `CHOSE: e1000 for network — 8086:100e (probed)` | `intent_manifest.py --target` |
| Minimality is already falsifiable, not aspirational: `REFUSED: 'tcp' requires 'mm', which is excluded. path: net -> mm` | `capability_slice.py` |
| A spec with no `excludes` is refused at build — *"without them, minimal cannot be tested"* | `build_service.py:232` `gate_leakage` |
| Identification is three-valued, so "not in the registry" never reads as "not present" | `target_spec.py`: *"probed but not in pci.ids: 1234:1111"* |
| The manifest is one dataclass with one constructor | `intent_manifest.Manifest`, built only by `build(sentence, input_device, target)` |

That last row is why this is cheap. The work is a **second constructor for an existing
dataclass**, not a second pipeline.

## Proposed Solution

```
  an application artifact              a target machine
    │                                    │
    ├─A1─ artifact record  ◄─────────────┤   what we know, and how we know it
    │      (per-fact provenance)         │   observed / declared / inferred / unknown
    │                                    │
    ├─A2─ static analysis                │   ELF: arch, interpreter, NEEDED, symbol versions
    ├─A3─ runtime observation            │   what it actually opened, loaded, bound
    │                                    │
    ├─A4─ artifact → Manifest ◄──────────┘   the SAME dataclass a sentence produces
    │        ╎
    │        ╎  ... capability_slice, derive_excludes, gate_leakage: unchanged ...
    │        ╎
    ├─A5─ substrate emission                 minimal container image
    ├─A6─ ablation score                     is "minimum" true?
    └─A7─ external probe                     does the application do its job?
```

A4 is the join, and it is the whole architectural claim: `build_from_artifact(...) -> Manifest`
returns the same frozen shape as `build(sentence, ...)`. Everything downstream —
`derive_excludes`, `capability_slice`, `intent_service`, `gate_leakage`, `package_image` — is
reused without modification. If A4 requires changing anything downstream, the design is wrong
and this PRD should be reconsidered rather than patched.

## The hard part is honesty, not extraction

Reading `NEEDED` out of an ELF is an afternoon's work. The reason this PRD is not one phase is
that **a derived manifest is always incomplete**, and an incomplete manifest that presents
itself as complete is the exact failure this project exists to prevent.

An application can reach for something no static pass will see:

- `dlopen("libssl.so.3")` from a config file read at start-up
- a code path that only runs when a feature flag is set
- a subprocess it execs on the first request
- a locale, a timezone database, a CA bundle, `/dev/urandom`

Ship a "minimal" image derived from static analysis alone and it boots, serves one request,
and dies on the second. That is worse than refusing, and it is the same class of error as the
phantom PCI id: a confident answer nobody can distinguish from a correct one.

So application facts carry provenance exactly as hardware facts do, and the vocabulary is
deliberately the same one `target_spec` already uses:

| Source | Meaning | Example |
|---|---|---|
| `observed` | we watched it happen | `dlopen` seen under A3 tracing |
| `declared` | a human or a manifest said so | `EXPOSE 8080`, a `--port` flag |
| `inferred` | derived from structure, not behaviour | `NEEDED libssl.so.3` in the ELF header |
| `unknown` | we looked and could not tell | syscall set of a statically linked Go binary |

**`unknown` is not a softer kind of absent.** A manifest carrying `unknown` facts may still be
built, but the build says so and the probe result is reported against it. An environment
derived entirely from `inferred` facts is a hypothesis, and A6 is how it gets tested.

## A6 is the point of the PRD

Everything above produces a claim: *this application needs exactly these things.* A6 is the
only phase that can falsify it, and without it the rest is a well-organised guess.

Three ways a manifest can be wrong, and one check each:

| Failure | What it looks like | Caught by |
|---|---|---|
| **Under-claim** — it needs something the manifest omits | image builds, app fails or misbehaves | A7, the external probe |
| **Leakage** — something excluded is present anyway | the image is not minimal, but works | `gate_leakage`, already built |
| **Over-claim** — the manifest requires what it does not need | works fine, is not minimal, and nothing notices | **A6 alone** |

Over-claim is the interesting one, because it is invisible to every other check. An image that
carries a library nothing loads passes the probe, passes leakage, boots, serves traffic — and
is not the minimum environment. A tool that claims minimality and cannot detect over-claim is
making an unfalsifiable claim.

**The ablation score.** For each capability in `requires`, rebuild the substrate without it and
run the probe:

- the probe **must fail** → the capability was load-bearing, the claim is honest
- the probe **passes** → the capability was not needed, the manifest over-claimed

Score is `N of N` required capabilities proved load-bearing, and it is reported with the image
the way injected-bug scores are reported with a suite. This is the same methodology the host
suites already use — inject a known defect, require the suite to catch it — pointed at an
environment instead of an implementation.

A manifest that cannot survive ablation has not earned the word *minimum*.

## What we are NOT building

- **AUTON's kernel as the target.** The intent-to-OS PRD states the boundary: *"Not a
  general-purpose OS. No POSIX, no libc, no shell."* A Django app needs CPython, which needs
  libc, POSIX, an ELF loader, a filesystem, threads and `mmap`. Building that is larger than
  everything in this repository to date and contradicts the scope that makes the current work
  tractable. **The substrates here are the ones the control plane already drives** — `docker`,
  `kubernetes`, `server`, `os`. The kernel stays the long game and is untouched by this PRD.
- **A package manager.** Resolving a dependency graph across versions and distributions is a
  solved, enormous problem. This derives what an artifact reaches for; it does not decide which
  version of it to fetch.
- **Reproducible builds.** Worth having, orthogonal, not this.
- **Guessing ports from a binary.** A listening port is `declared` or `observed`, never
  `inferred`. Static analysis cannot know it and must not pretend to.
- **Multi-application images in v1.** One artifact, one environment.

## Success Metrics

| Metric | Today | Target |
|---|---|---|
| Applications compilable to a running minimal environment | 0 | **≥3**, in different runtimes |
| Manifest facts with no recorded provenance | n/a | **0** — refused by the validator |
| Required capabilities proved load-bearing by ablation | n/a | **N of N** |
| Over-claims caught before release | n/a | reported, not zero — a zero here means A6 is not running |
| Downstream files changed to accommodate the artifact path | n/a | **0** |
| Dynamic-only dependency (`dlopen`) caught by A3 and missed by A2 | n/a | **≥1**, proving the layers are not redundant |

The fourth row is deliberate. A minimisation tool that has never reported an over-claim is not
a tool that never over-claims.

## Implementation Phases

| # | Phase | Gate that decides it | Depends on |
|---|---|---|---|
| A1 | Artifact record + validator, per-fact provenance | `artifact_spec.py --validate` refuses a fact with no source, and names what is missing — mirroring `target_spec.missing_facts` | — |
| A2 | Static analysis: arch, interpreter, `NEEDED`, minimum symbol versions, static vs dynamic | a corpus of binaries with known answers; **scored by injecting a lie** — a fact the analyser did not observe must never appear as `observed` | A1 |
| A3 | Runtime observation: run it, record what it opened, loaded and bound | an application whose only dependency is `dlopen`ed is caught here and **missed by A2**. If A2 catches it, one of the two is not doing its job | A1 |
| A4 | `build_from_artifact(...) -> Manifest` | a contradictory artifact manifest is refused with the dependency path, exactly as a sentence one is; **zero downstream files changed** | A2, A3 |
| A5 | Substrate emission: manifest → minimal container image | the image builds and the application starts | A4 |
| A6 | **The ablation score** | every capability in `requires` removed in turn; the probe must fail each time. `N of N` or the manifest over-claimed | A5, A7 |
| A7 | External probe, graded outside the image | `run-intent-probe.sh`'s rubric: `WORKED` / `HONESTLY REFUSED` / `FAILED`. A log line saying "started" is the image grading itself | A5 |
| D-A1 | **Decision**: first substrate — container, or microVM | a written verdict in `decisions/first-substrate.md` | owner |
| D-A2 | **Decision**: how far to go on syscalls and seccomp | a written verdict in `decisions/syscall-scope.md` | owner |

### On D-A2, before anyone starts it

Syscall extraction is the most attractive and least tractable part of this idea. Static
extraction is defeated by indirect calls and by any interpreter; dynamic extraction is only as
complete as the paths exercised, so a seccomp profile derived from one run will kill the
process on the first unexercised branch.

A seccomp profile that is *almost* right is a production outage with a confusing error
message. It should be opt-in, reported with the coverage it was derived from, and never the
default. That is a decision worth taking deliberately rather than discovering.

## Open Questions

1. **Is ablation affordable?** A6 rebuilds and re-probes once per required capability. For a
   manifest with thirty entries that is thirty builds. Caching layers makes it cheaper; a
   sampling strategy makes it weaker. Unknown until measured.
2. **What is the unit of a capability for an application?** For the kernel it is a subsystem
   with declared `provides`/`depends`. For an application it might be a shared library, a
   syscall group, a filesystem path, or a service it dials. Getting this wrong makes the
   manifest either useless or unbuildable, and it is the first thing A1 has to settle.
3. **Does the existing capability vocabulary stretch?** `capability_slice` closes over the
   kernel's subsystem graph. Application capabilities may need a second, disjoint index rather
   than entries bolted into the first.
4. **Is `declared` trustworthy enough to build on?** `EXPOSE 8080` in a Dockerfile is a
   comment, not a contract. It may deserve its own weaker source than `declared`.

## Decisions Log

| Decision | Why |
|---|---|
| A second constructor, not a second pipeline | The manifest, the slice, the refusal and the leakage gate already exist and already work. A parallel path would duplicate them and drift |
| Application facts carry provenance, like hardware facts | The phantom-PCI-id failure, one layer up. A derived dependency presented as an observed one is indistinguishable from a correct answer until production |
| Ablation is a phase, not a nice-to-have | Over-claim is invisible to every other check. Without A6 "minimum" is an unfalsifiable claim, and this project does not make those |
| Container and VM substrates first; not AUTON's kernel | The kernel has no POSIX by design. Targeting it would require reversing a stated scope boundary and is a larger project than everything done so far |
| A new PRD rather than phases in `auton-completion` | That document is the finish line for work already defined, and every open row there waits on a generation run. These phases wait on nothing and would blur what "completion" means |
| Ports are never `inferred` | Static analysis cannot know a listening port. A tool that guesses one produces an image that fails in a way nobody can trace back to the guess |
