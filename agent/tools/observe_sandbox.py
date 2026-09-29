"""The sandbox `observe.py` runs a subject in (application-to-environment A5).

The subject is untrusted (`agent/kernel_spec/decisions/subject-trust.md`,
decided 2026-09-29): it runs in a disposable container with no network, a
read-only root, every capability dropped but the tracer's, no host mounts, no
host environment, and hard limits. Isolated in this module so the microVM
substrate (first-substrate.md: "both, container first") changes one file.

Building the image is separate from running it and does use the network: a
subject's dependencies have to come from somewhere. The *run* — the only
thing observed — does not.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

TRACER_LAYER = (
    "RUN (command -v strace >/dev/null) || "
    "(apt-get update && apt-get install -y --no-install-recommends strace "
    "&& rm -rf /var/lib/apt/lists/*) || apk add --no-cache strace\n"
)

# The traced program runs in the background, the exercise in the foreground,
# untraced. Ending the run signals the *tracee*, not strace: strace ignores a
# TERM while its tracee is alive (found capturing the flask trace), and exits
# on its own once the tracee does.
WRAPPER = r'''
printf '%s' "$AUTON_EXERCISE" > /tmp/auton-exercise
strace -f -qq -s 256 -o /tmp/auton-trace -- "$@" >/tmp/auton-app.log 2>&1 &
S=$!
sleep "$AUTON_WARMUP"
EX=0
if [ -s /tmp/auton-exercise ]; then sh /tmp/auton-exercise >/tmp/auton-exercise.log 2>&1; EX=$?; fi
for p in /proc/[0-9]*; do
  n=${p#/proc/}
  [ "$n" = 1 ] || [ "$n" = "$S" ] || kill -TERM "$n" 2>/dev/null
done
i=0
while kill -0 "$S" 2>/dev/null && [ $i -lt 10 ]; do sleep 1; i=$((i+1)); done
kill -KILL "$S" 2>/dev/null
wait "$S" 2>/dev/null
echo "===AUTON-EXIT exercise=$EX==="
echo "===AUTON-TRACE==="; cat /tmp/auton-trace
echo "===AUTON-END==="
'''


@dataclass(frozen=True)
class Limits:
    memory: str = "1g"
    pids: int = 256
    cpus: str = "2"
    wall_seconds: int = 300
    warmup_seconds: int = 3


def image_tag(subject: Path) -> str:
    digest = hashlib.sha256(str(Path(subject).resolve()).encode()).hexdigest()[:12]
    return f"auton-observe-{digest}"


def build(subject: Path, tag: str) -> str:
    """Build the subject's own Dockerfile, then add a tracer layer. Returns the
    traced image's id. Refuses a subject with no Dockerfile: how the
    application is assembled is the subject's to declare, not ours to guess."""
    subject = Path(subject)
    if not (subject / "Dockerfile").is_file():
        raise RuntimeError(f"{subject} has no Dockerfile; observe.py runs the application "
                           f"as its own Dockerfile builds it, or not at all")
    _docker(["build", "-q", "-t", f"{tag}-app", str(subject)])
    _docker(["build", "-q", "-t", tag, "-"], stdin=f"FROM {tag}-app\n{TRACER_LAYER}")
    return _docker(["image", "inspect", "--format", "{{.Id}}", tag]).strip()


def command_of(tag: str) -> list[str]:
    """The image's own ENTRYPOINT + CMD: what it runs when nobody overrides it."""
    cfg = json.loads(_docker(["image", "inspect", "--format", "{{json .Config}}", tag]))
    cmd = (cfg.get("Entrypoint") or []) + (cfg.get("Cmd") or [])
    if not cmd:
        raise RuntimeError(f"{tag} declares no ENTRYPOINT or CMD; pass --command")
    return cmd


def run_argv(tag: str, command: list[str], exercise: str, limits: Limits) -> list[str]:
    """The docker argv. Every isolation flag is here and asserted by test."""
    return [
        "docker", "run", "--rm",
        "--network", "none",
        "--read-only", "--tmpfs", "/tmp:rw,exec,size=256m",
        "--cap-drop", "ALL", "--cap-add", "SYS_PTRACE",
        "--security-opt", "no-new-privileges",
        "--pids-limit", str(limits.pids),
        "--memory", limits.memory,
        "--cpus", limits.cpus,
        "--env", f"AUTON_EXERCISE={exercise}",
        "--env", f"AUTON_WARMUP={limits.warmup_seconds}",
        "--entrypoint", "sh",
        tag, "-c", WRAPPER, "sh", *command,
    ]


def run(tag: str, command: list[str], exercise: str, limits: Limits) -> tuple[str, int]:
    """Run once; return (trace text, exercise exit status)."""
    out = subprocess.run(run_argv(tag, command, exercise, limits), capture_output=True,
                         text=True, errors="replace", timeout=limits.wall_seconds)
    text = out.stdout
    if "===AUTON-TRACE===" not in text:
        raise RuntimeError(f"the sandbox produced no trace (docker exit {out.returncode}): "
                           f"{out.stderr.strip()[:500]}")
    head, _, rest = text.partition("===AUTON-TRACE===\n")
    trace = rest.partition("===AUTON-END===")[0]
    exit_line = head.rsplit("===AUTON-EXIT exercise=", 1)[-1]
    return trace, int(exit_line.split("=")[0].strip() or 0)


def _docker(args: list[str], stdin: str | None = None) -> str:
    r = subprocess.run(["docker", *args], input=stdin, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args[:2])} failed: {r.stderr.strip()[:800]}")
    return r.stdout
