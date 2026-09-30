# Pre-registration: three applications, three runtimes, end to end (w22)

**Written 2026-09-29, before any w22 run.** Plan: [`w22-app-three-runtimes`](../plans/completed/w22-app-three-runtimes.plan.md).
Driver: `scripts/app_to_env.py` (analyst → manifest → packager → observe → regate → probe → ablate).

## Subjects, pinned before the Analyst sees them

| Runtime | Repository | Commit | Subject path | Probe (operator-written) |
|---|---|---|---|---|
| Python | `pallets/flask` | `d73fa1cdcbd8b1465c151db8924ba58b1dd14e35` | `examples/javascript` | `agent/tests/fixtures/probes/js-example.yaml`: `GET :5000/` → 200, body contains "JavaScript" |
| Node | `heroku/node-js-getting-started` | `7233acafd6e9aa0a8cce2cd05188d0ae8f03ee8f` | repo root | `node-getting-started.yaml`: `GET :5006/` → 200 |
| Go (static) | `traefik/whoami` | `1ce75d01b6978863647da42557a707a479da3a51` | repo root | `whoami.yaml`: `GET :80/` → 200 containing "Hostname"; `GET /health` → 200 |

None was chosen or adjusted after seeing an Analyst's output. The probes were written from each
repository's README and entry point before any run. The operator here is Claude acting for the
owner, and the report says so.

## Model and budget

`ollama_chat/qwen3.5:9b` for both agent stages, 2 h per stage. Same loop commit for all three,
recorded in each `STAGES.json` directory.

## What each outcome means

Each subject ends at exactly one stage, recorded in `STAGES.json`:

| Ends at | Meaning |
|---|---|
| `ablate` passed | the application compiled to a running environment, scored |
| `analyst` | the model could not produce a record the gate accepts (A4 held; the model failed) |
| `packager` | no recipe passed the build gate |
| `observe` / `regate` | observation found a need the package lacks: an under-claim caught before release |
| `probe` | the package builds and starts but does not work, judged from outside |

**Fallback, stated now.** If an agent stage fails, the subject is re-run once from that stage with
a human-written artifact (`--record`) or recipe (`--recipe`), labelled `author: human`. That
separates "the pipeline works" from "the model can drive it". The PRD's first metric counts
only fully agent-driven subjects. The fallback count is reported beside it.

## Predictions

- **whoami**: the Packager must write a multi-stage Go build. `observe` cannot trace a `scratch`
  image, which has no shell to host the tracer gate, so this subject is predicted to stop at
  `observe`. It would be reported as a coverage gap in A5, not worked around.
- **Node**: the Analyst over-claims libraries, as the 9b model did on the fixture (it copied the
  index). Ablation reports most of them over-claimed.
- **Python (js_example)**: the most likely full pass. Predicted over-claims include
  `/etc/ssl/certs` again.

## Amendment, before any w22 run

The `whoami` prediction above names a coverage gap in A5, and the gap was closed before any w22
run started. The observation image now carries its own static busybox for the tracer handshake:
instrumentation, like the tracer, and never part of the package. Observing `whoami` from its own
`scratch` Dockerfile then worked (`listen:tcp/80`; a failed open of `/etc/localtime`; its CA
bundle and zoneinfo never opened).

**Revised prediction for whoami:** it reaches `ablate`, if the Packager writes a Go build that
passes the gate. The CA bundle and `/usr/share/zoneinfo` come out over-claimed if the Analyst
claims them.

## Probe self-test, before any w22 run

Every probe was run against a human-written reference build of its own application, and
against the wrong one, the way a gate suite is scored against a reference:

| Probe | Own reference image | Wrong application |
|---|---|---|
| js-example | WORKED (1 check) | FAILED against the node image (connection refused on :5000) |
| node-getting-started | WORKED (1 check) | FAILED against whoami |
| whoami | WORKED (2 checks) | FAILED against js-example |

The reference recipes are in `agent/tests/fixtures/recipes/`, labelled human. `whoami` uses its
own upstream Dockerfile. These are also the fallback recipes the pre-registration names.
