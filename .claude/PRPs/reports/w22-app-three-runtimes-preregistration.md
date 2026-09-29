# Pre-registration: three applications, three runtimes, end to end (w22)

**Written 2026-09-29, before any w22 run.** Plan: [`w22-app-three-runtimes`](../plans/w22-app-three-runtimes.plan.md).
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
