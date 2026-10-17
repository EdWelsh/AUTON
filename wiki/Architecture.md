# Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                       Orchestration Engine                         │
│              (VibeTensor-style loop; git is the bus)               │
│  plan → design → develop → syntax gate → review → test → integrate │
└───────┬──────────────────┬──────────────────┬──────────────┬──────┘
        │                  │                  │              │
   Kernel swarm        SLM swarm        Hardware research   App → env
        │                  │                  │              │
 .artifacts/campaign  .artifacts/slm    .artifacts/hardware  run workspace
        └──────────────────┴────────┬─────────┴──────────────┘
                                    ▼
          Gates frozen before the run: tests/kernel/, eval.sh,
          neural_parity.sh, check_record, check_hardware_record
```

## The engine

`agent/orchestrator/core/engine.py` runs a goal through phases, checkpointing state so a run
can pause and resume (`auton run --resume`):

| Phase | What happens |
|---|---|
| planning | the manager decomposes the goal into a task graph; fixed seed tasks are added for roles whose plan is not a model's to make (the Analyst, the Packager) |
| designing | the architect writes interface headers |
| developing | developers and specialists implement tasks on branches: write, build, fix, test, commit |
| syntax gate | code that does not compile never reaches a reviewer |
| review | the reviewer sees the whole diff in its prompt, plus each matching specialist's checklist; it may run the run's frozen gates (`run_gate`) |
| integrating | approved branches merge to `main`; the composition validator builds and runs unit tests on the merged tree |
| paused / done / error | a git fault or a memory-guard pause saves state and is resumable; a run ends `done` or `error` |

Workflow modes (`[workflow] mode`): `kernel_build` (default), `slm_training`, `dual`.

## Git is the message bus

Each agent works on its own branch (`agent/<agent-id>/<subsystem>-<component>`) in a git
workspace. There is no broker: tasks, messages and state live under `.auton/` in the
workspace (excluded from commits), and work moves by merge. A new workspace always starts on
`main`.

## The model client

`agent/orchestrator/llm/client.py` talks to any LiteLLM provider, Ollama, or Claude through
the subscription (`claude-cli/<model>`: each call is `claude -p`, tools described as JSON in
the prompt). When the subscription's limit is reached, calls can fall back to a local model
until it resets; the switch is logged and a run that crosses it is reported as mixed-model.

## Tools are the only actions

An agent may call only the tools its role was given; any other name is refused with the list
of what it does have. The `shell` tool is an allowlist (`make git clang gcc python python3 ls
cat grep find qemu-system-x86_64`), executed as an argument vector, never through a shell.
Internal tools run `create_subprocess_exec`, so a path containing `; touch x` is an argument,
not a command.

## Where things run

| Swarm | Launcher | Workspace (testing area) |
|---|---|---|
| Kernel build | `scripts/campaign.py` / `scripts/generation_run.py` | `.artifacts/campaign/<run>-attempt<k>/ws` |
| SLM | `scripts/slm_run.py` | `.artifacts/slm/<run>/ws` + `kernel/` base for parity and eval |
| Hardware research | `scripts/vendor_research.py` | `.artifacts/hardware/<run>/ws` |
| Application to environment | `scripts/app_to_env.py` | the run's workspace |

Full detail: [`docs/ARCHITECTURE.md`](https://github.com/EdWelsh/AUTON/blob/HEAD/docs/ARCHITECTURE.md).
