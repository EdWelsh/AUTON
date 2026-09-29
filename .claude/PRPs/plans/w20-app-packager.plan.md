# Plan: A8 — The Packager agent: validated manifest → deployable artifact

## Summary
A new `AgentRole.PACKAGER` turns a validated application Manifest (A6) into something the chosen
substrate runs — for a container substrate, a Dockerfile and build context; for a microVM, a
rootfs recipe. The agent writes the recipe, and tools judge it. It must build, the application
must start, and an **image inventory** (the libraries and paths actually present in the built
image) is compared against the manifest's `application` facts. Anything in the image that the
manifest did not ask for is reported the way `gate_leakage` reports an excluded subsystem present
in a kernel. Registration uses the same three-part gate as A3, because the failure it guards
against is the same one.

## User Story
As the owner, I want the environment built from the manifest and nothing else, and a list of
anything that got in anyway.

## Problem → Solution
No role packages; "minimal" has no check on the container side →
Packager (role, prompt, tools, three-part registration) + `image_inventory.py` + a pre-review
gate that builds the recipe and diffs the inventory against the manifest.

## Metadata
- **Complexity**: Large
- **Source PRD**: `prds/auton-application-to-environment.prd.md`
- **PRD Phase**: A8 (settles Open Question 4: Packager is a separate role — the Integrator merges branches, and a failing package build must not block a merge)
- **Estimated Files**: 11
- **Depends on**: A6; **D-A1** (`first-substrate.md` verdict) decides which recipe kind is built first

---

## Mandatory Reading

| Priority | File | Why |
|---|---|---|
| P0 | `.claude/PRPs/plans/w18-app-analyst.plan.md` | the three-part registration this repeats |
| P0 | `agent/tools/build_service.py:232-300` | `gate_leakage` — what "present but excluded" reporting looks like |
| P0 | `agent/orchestrator/core/syntax_gate.py` | pre-review gate hook |
| P0 | `agent/tools/package_image.py:1-60` | the kernel-side packager's provenance rules ("an intent that cannot be built produces a package that says so") |
| P1 | `controlplane/src/controlplane/backends/docker/client.py` | argv-only docker invocation |
| P1 | `agent/kernel_spec/decisions/first-substrate.md` | the substrate verdict |

## Files to Change

| File | Action | Justification |
|---|---|---|
| `agent/orchestrator/agents/base_agent.py` | UPDATE | `AgentRole.PACKAGER` |
| `agent/orchestrator/agents/packager_agent.py` | CREATE | role |
| `agent/orchestrator/llm/prompts.py`, `tools.py` | UPDATE | prompt; `PACKAGER_TOOLS` = read/write/edit/list/search + `git_commit`; `shell` limited to `docker build` via a dedicated `build_package` tool, not the general allowlist |
| `agent/orchestrator/core/engine.py`, `manager_agent.py` | UPDATE | construct + register + advertise (only when a manifest has a substrate) |
| `agent/tools/image_inventory.py` | CREATE | built image → `{libs, paths, execs}` via `docker run --rm --network none <img> sh -c 'find … ; ldconfig -p'` or, for distroless, `docker export` + tar listing |
| `agent/tools/package_gate.py` | CREATE | build → inventory → diff against `manifest.application` → `extras`, `missing`; missing is a failure, extras are a report |
| `agent/orchestrator/core/syntax_gate.py` | UPDATE | changed `package/Dockerfile` → `package_gate` before review |
| `agent/tests/unit/orchestrator/test_packager_registration.py` | CREATE | three-part gate |
| `agent/tests/unit/test_package_gate.py` | CREATE | inventory diff on recorded inventories |
| `agent/tests/integration/test_package_flask_hello.py` | CREATE | the fixture app packaged, built, started (skips without docker) |

## NOT Building
- A registry push or deployment to a remote host (the control plane's `server`/`kubernetes` backends do that later, unchanged).
- The external probe (A10) or ablation (A9).
- Base-image selection by model. The base per `runtime:` is a table entry (`app_spec/bases.yaml`, pinned by digest); the agent may not choose an unlisted base.

---

## Step-by-Step Tasks

### Task 1: Registration tests (RED)
- **ACTION**: mirror A3's: constructed, registered, advertised only when relevant, a `packager` task dispatched.

### Task 2: Base table and inventory
- **ACTION**: `bases.yaml` (`runtime:python-3.12` → `python:3.12-slim@sha256:…`, `runtime:static-elf` → `scratch`); `image_inventory` on two recorded images → stable output.

### Task 3: The gate
- **ACTION**: `package_gate`: refuse a Dockerfile whose `FROM` is not the table's base for the manifest's runtime; build with `--network` allowed only for the base pull (then `--pull=never` in the gate's re-build); inventory; `missing` → exit 1 with names; `extras` → exit 0 with a report saved beside the recipe.

### Task 4: Role and prompt
- **ACTION**: prompt: build only what `manifest.application` names; record in `package/PROVENANCE.json` which fact each Dockerfile line satisfies (mirrors `package_image`'s "which spec section each artifact implements").

### Task 5: Fixture proof
- **ACTION**: `flask-hello` from A3: scripted Packager writes the recipe; gate builds; the container starts and logs its listen line. (Whether it *works* is A10's question, not this one.)

## Validation Commands
```bash
cd agent && ../.venv/bin/python -m pytest tests/unit/orchestrator/test_packager_registration.py tests/unit/test_package_gate.py -q
cd agent && ../.venv/bin/python -m pytest tests/integration/test_package_flask_hello.py -q
```

## Acceptance Criteria
- [ ] A `packager` task is dispatched (three-part gate).
- [ ] An unlisted base is refused; a missing manifest capability fails the gate; extras are reported, not hidden.
- [ ] The fixture app's image builds and the application starts.

## Risks
| Risk | Mitigation |
|---|---|
| Slim bases carry hundreds of libs the app never loads → huge `extras` | expected and correct; it is the baseline A9 measures against. Report it; do not suppress it |
| `docker build` needs network | only for the pinned base pull, then `--pull=never` |
