# Repository Layout

**The repository holds the agents that create kernels, not kernels.** Generated trees live in
testing areas; vendor documents and fetched text live in caches; both are gitignored.

```
AUTON/
├── agent/                     the agents and everything they read
│   ├── orchestrator/          engine, agents, LLM client, tools, validation
│   ├── kernel_spec/           the kernel specification (+ specialists.yaml)
│   ├── slm_spec/              the SLM specification (bannered: SLM/DATA.md governs)
│   ├── app_spec/              application capability index (application-to-environment)
│   ├── hardware/              vendor inventory and registry, ISA tables, errata, exceptions
│   ├── tools/                 deterministic tools: registry, ISA, gates, ingest, packaging
│   ├── config/                auton.toml.example (copy to auton.toml)
│   └── tests/                 ~2,200 unit and integration tests
├── SLM/                       the on-device model: datasets, tools, training, export, tests
│   ├── DATA.md                what data an in-kernel model needs, and what fits
│   ├── datasets/              generated corpora (os_chat, hardware_kernel, hardware_reference)
│   └── data/sources.yaml      domain-text sources and licences
├── tests/kernel/              frozen host gate suites + hand-written references (the only kernel C code tracked)
├── tests/eval/                the 65-prompt chat eval and its rubric
├── tests/conformance/         silicon conformance harness
├── scripts/                   launchers: campaign, slm_run, vendor_research, app_to_env, e2e, eval, wiki
├── controlplane/              the host control plane (macOS, Linux, Windows)
├── docs/                      architecture, open work, campaign, generation queue, host matrix
├── wiki/                      this wiki's source
└── .claude/PRPs/              PRDs, plans and reports: the project's research record
```

## Runtime areas (gitignored)

| Path | Holds |
|---|---|
| `.artifacts/campaign/<run>-attempt<k>/` | a campaign run: `ws/` (the generated kernel tree), sessions, gate logs, `RESULT.json` |
| `.artifacts/slm/<run>/` | an SLM run: `ws/`, `kernel/` (base tree for parity and eval), log |
| `.artifacts/hardware/<run>/` | a vendor research run: `ws/` with `hardware/proposals/`, `hardware/derived/` |
| `.artifacts/wiki/` | the wiki clone `scripts/wiki.py publish` pushes from |
| `.cache/vendor/<vendor>/<doc>/` | fetched vendor documents, each with `provenance.json` |
| `.cache/slm/domain/<source>/` | fetched domain text |
| `agent/workspace/` | agent workspaces; the default `--workspace` of `auton status`, `auton agents` and `auton tasks` (`workspace`, relative to the current directory, so `agent/workspace/` when run from `agent/`) |
| `kernels/` | where an ad-hoc `auton run` writes unless `--workspace` says otherwise: `[workspace].path` (`../kernels/x86_64` from `agent/` in the example config), else `kernels/<arch>`; also a base tree for docker compose (`scripts/kernel-base.sh kernels/x86_64`) |
| `SLM/work/`, `SLM/models/` | the e2e spine's checkpoints and exports |

## Where the record is

`.claude/PRPs/prds/` (product requirements), `plans/` (every plan, `completed/` for done
ones), `reports/` (every run's report, failures included). `docs/OPEN-WORK.md` is the index
of what is unfinished. The latest drift audit is
[`w26`](https://github.com/EdWelsh/AUTON/blob/HEAD/.claude/PRPs/plans/w26-drift-and-slm-readiness.plan.md).
