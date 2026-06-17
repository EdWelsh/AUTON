# AUTON Control Plane

The AUTON **host chat control plane** — one natural-language chat that runs real
workloads on your machine: desktop apps (macOS/Linux/Windows), Docker containers,
Kubernetes deployments, and server processes. The same conversation is reachable
from a **terminal**, a **web UI**, and a **desktop app**, backed by one shared
session.

It mirrors the in-kernel role registry (`kernels/x86_64/kernel/slm/roles.c`): every
action is a sentence routed to a *capability*.

## Install

```bash
pip install -e controlplane            # core
pip install -e 'controlplane[ui]'      # + web UI surface
pip install -e 'controlplane[desktop]' # + desktop app surface
pip install -e 'controlplane[llm]'     # + free-form NL intent (agent LLM client)
```

Console scripts: `auton-chat` (terminal), `auton-ui` (web), `auton-desktop` (app).

## Architecture

```
controlplane/src/controlplane/
  core/        contract.py  registry.py  router.py  session.py  chat.py   # frozen contract
  backends/    desktop/  docker/  kubernetes/  server/  status/           # one plugin.py each
  surfaces/    terminal/  ui/  desktop/                                   # install targets
  intent/      free-form NL -> capability (LLM) with deterministic fallback
```

## Writing a backend

A backend is a subpackage `controlplane.backends.<name>` with a `plugin.py`:

```python
from controlplane.core import Capability, CapabilityResult, CapabilityStatus

def _run(text: str) -> CapabilityResult:
    # parse sub-command from text, run the REAL tool, return a result
    return CapabilityResult.ok("done", detail=...)

def get_capabilities() -> list[Capability]:
    return [
        Capability(
            name="docker",
            keywords=("docker", "container"),
            status=CapabilityStatus.WORKING,
            note="run/list/stop containers via the docker CLI",
            handler=_run,
        ),
    ]
```

The registry discovers it automatically — no shared file to edit.

## Test

```bash
python -m pytest controlplane/tests -q
```
