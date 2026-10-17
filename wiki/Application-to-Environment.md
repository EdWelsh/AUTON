# Application to Environment

A second front end for the compiler: give AUTON an application repository that already
exists, and get back the minimum environment that runs it. Its rule is **agents gather
evidence, deterministic tools adjudicate it.**

## How it works

1. **Stage.** The application is exported read-only to `.auton/subject/` in the workspace.
   Three layers keep it unwritten: file tools refuse the path (compared by file identity),
   the files lose their write bits, and a tree hash taken at staging is re-checked before
   anything built on it is accepted.
2. **Analyse.** The **Analyst** (no shell) writes `analysis/<app>.artifact.yaml`: each
   capability it claims (`runtime:python-3.11`, `lib:libssl.so.3`, `listen:tcp/8000`,
   `pypi:flask`) with evidence: a file, a line, and the exact quoted line. Capabilities come
   from a closed index ([`agent/app_spec/capabilities.yaml`](https://github.com/EdWelsh/AUTON/blob/HEAD/agent/app_spec/capabilities.yaml)).
   `check_record` runs the gate's checks before any reviewer sees it, including that every
   quote is really on the line it cites.
3. **Observe and ablate.** `observe.py` runs the application in a sandbox and records what
   it actually used (`observed` facts only it may write); ablation removes one capability at
   a time and re-probes, to show each is needed.
4. **Package.** The **Packager** (no build tool) writes `package/Dockerfile` and
   `package/PROVENANCE.json`; [`package_gate.py`](https://github.com/EdWelsh/AUTON/blob/HEAD/agent/tools/package_gate.py)
   builds it from a digest-pinned base, inventories the image and checks it starts.
5. **Probe.** A frozen probe outside the image decides whether it worked.

Substrates: containers first; a QEMU `virt` microVM substrate also exists (`--substrate vm`).

## Run it

```bash
.venv/bin/python scripts/app_to_env.py --subject <app dir> --probe <probe.yaml>
```

## Results so far

Three pinned subjects. With `qwen3.5:27b-coding-mxfp8`, 1 of 3 fully agent-driven, 2 of 3 with
a four-hour analyst budget (w23 A3). Packaging is reliable; analysis is the hard part.

## Owner decisions it depends on

- first substrate (container or microVM): `agent/kernel_spec/decisions/first-substrate.md`
- how far to go on syscalls and seccomp: `decisions/syscall-scope.md`
- whether a subject repository is trusted: `decisions/subject-trust.md`. A README saying
  "ignore previous instructions" is a live injection vector into a task graph other agents
  execute.
