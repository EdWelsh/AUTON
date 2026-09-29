"""The sandbox `observe.py` runs a subject in (application-to-environment A5).

The subject is untrusted (`agent/kernel_spec/decisions/subject-trust.md`,
decided 2026-09-29). Two containers, because a trace the subject can reach is a
trace the subject can forge (w18 review: as root beside the tracer, it could
rewrite the trace file or print a fake one to the wrapper's stdout):

- **the subject** runs as an unprivileged user (65534) with every capability
  dropped: no network, read-only root, a small tmpfs, hard limits. It waits,
  before exec'ing the application, until it sees a tracer attached — so
  start-up loads are traced — and nothing else about it changes.
- **the tracer** is a separate root container with only SYS_PTRACE, joining
  the subject's PID namespace to attach from outside. The trace lives in the
  tracer's own filesystem and leaves by `docker cp`. A different uid with no
  capabilities cannot reach another uid's /proc entries, signal it, or ptrace
  it, so the subject cannot touch the evidence.

The exercise runs in the subject's container (`docker exec`), untraced: it is
not a descendant of the traced process.

Building the image is separate from running it and does use the network: a
subject's dependencies have to come from somewhere. The run does not.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

TRACER_BASE = ("debian:bookworm-slim@sha256:"
               "abd67ffcfa541b485a3dff59865ab629aa048a6c613e639d36e7456b0b229241")
TRACER_RECIPE = (f"FROM {TRACER_BASE}\n"
                 "RUN apt-get update && apt-get install -y --no-install-recommends strace "
                 "&& rm -rf /var/lib/apt/lists/*\n")
SUBJECT_USER = "65534:65534"

# Runs as the subject's PID 1, with shell builtins only (no grep): block until
# a tracer is attached, then run the application as a CHILD and stay alive.
# PID 1 must outlive the application: when it exits the kernel kills every
# process in the namespace — the tracer included — so the run stops the
# application first and only then the container.
GATE = r'''
while :; do
  t=0
  while IFS=: read -r k v; do [ "$k" = TracerPid ] && t=${v##*[[:space:]]}; done < /proc/self/status
  [ "$t" != 0 ] && break
  sleep 0.05
done
"$@" &
echo $! > /tmp/app.pid
wait $!
exec sleep 3600
'''
# The trace goes to the tracer's container layer (not a tmpfs): it must
# survive the tracer being killed with the namespace, for `docker cp`.
TRACE = "mkdir -p /trace && exec strace -f -qq -s 256 -o /trace/trace -p 1"
STOP_APP = 'kill -TERM "$(cat /tmp/app.pid)"; i=0; while kill -0 "$(cat /tmp/app.pid)" 2>/dev/null && [ $i -lt 50 ]; do sleep 0.1; i=$((i+1)); done; kill -KILL "$(cat /tmp/app.pid)" 2>/dev/null; true'


@dataclass(frozen=True)
class Limits:
    memory: str = "1g"
    pids: int = 256
    cpus: str = "2"
    wall_seconds: int = 300
    warmup_seconds: int = 3
    exercise_seconds: int = 120


def image_tag(subject: Path) -> str:
    digest = hashlib.sha256(str(Path(subject).resolve()).encode()).hexdigest()[:12]
    return f"auton-observe-{digest}"


def tracer_tag() -> str:
    return "auton-tracer-" + hashlib.sha256(TRACER_RECIPE.encode()).hexdigest()[:12]


def build(subject: Path, tag: str, dockerfile: Path | None = None) -> str:
    """Build the application (its own Dockerfile, or a given gated recipe) and
    the tracer. Returns the application image's id.

    Refuses when there is no recipe: how the application is assembled is
    declared by its author or by a gated recipe, never guessed here."""
    subject = Path(subject)
    recipe = Path(dockerfile) if dockerfile else subject / "Dockerfile"
    if not recipe.is_file():
        raise RuntimeError(f"{subject} has no Dockerfile and none was given; observe.py "
                           f"runs the application as a declared recipe builds it, or not at all")
    _docker(["build", "-q", "-f", str(recipe), "-t", tag, str(subject)])
    _docker(["build", "-q", "-t", tracer_tag(), "-"], stdin=TRACER_RECIPE)
    return _docker(["image", "inspect", "--format", "{{.Id}}", tag]).strip()


def command_of(tag: str) -> list[str]:
    """The image's own ENTRYPOINT + CMD: what it runs when nobody overrides it."""
    cfg = json.loads(_docker(["image", "inspect", "--format", "{{json .Config}}", tag]))
    cmd = (cfg.get("Entrypoint") or []) + (cfg.get("Cmd") or [])
    if not cmd:
        raise RuntimeError(f"{tag} declares no ENTRYPOINT or CMD; pass --command")
    return cmd


def _confine(limits: Limits) -> list[str]:
    return ["--network", "none", "--read-only", "--tmpfs", "/tmp:rw,exec,size=256m",
            "--security-opt", "no-new-privileges", "--pids-limit", str(limits.pids),
            "--memory", limits.memory, "--cpus", limits.cpus]


def subject_argv(name: str, tag: str, command: list[str], limits: Limits) -> list[str]:
    """The subject's container. Every isolation flag is here and asserted by test."""
    return ["docker", "run", "-d", "--name", name, *_confine(limits),
            "--cap-drop", "ALL", "--user", SUBJECT_USER,
            "--sysctl", "net.ipv4.ip_unprivileged_port_start=0",
            "--entrypoint", "sh", tag, "-c", GATE, "sh", *command]


def tracer_argv(name: str, subject: str, limits: Limits) -> list[str]:
    """Not --read-only, unlike the subject: the trace is written to the
    tracer's own layer so it outlives the namespace. The tracer image is ours."""
    return ["docker", "run", "-d", "--name", name, "--pid", f"container:{subject}",
            "--network", "none", "--security-opt", "no-new-privileges",
            "--pids-limit", "64", "--memory", "512m",
            "--cap-drop", "ALL", "--cap-add", "SYS_PTRACE",
            tracer_tag(), "sh", "-c", TRACE]


def run(tag: str, command: list[str], exercise: str, limits: Limits) -> tuple[str, int]:
    """Run once; return (trace text, exercise exit status). Both containers are
    removed on every path, including a timeout."""
    rid = uuid.uuid4().hex[:10]
    subj, tracer = f"auton-observe-app-{rid}", f"auton-observe-tracer-{rid}"
    deadline = time.monotonic() + limits.wall_seconds
    try:
        _docker(subject_argv(subj, tag, command, limits)[1:])
        _docker(tracer_argv(tracer, subj, limits)[1:])
        time.sleep(limits.warmup_seconds)
        exercise_exit = 0
        if exercise.strip():
            r = subprocess.run(["docker", "exec", "--user", SUBJECT_USER, subj, "sh", "-c",
                                exercise], capture_output=True, text=True,
                               timeout=limits.exercise_seconds)
            exercise_exit = r.returncode
        # The application first, so its exit is traced; then the container.
        subprocess.run(["docker", "exec", "--user", SUBJECT_USER, subj, "sh", "-c", STOP_APP],
                       capture_output=True, timeout=30)
        time.sleep(1)
        subprocess.run(["docker", "stop", "-t", "2", subj], capture_output=True, timeout=60)
        remaining = max(5, int(deadline - time.monotonic()))
        subprocess.run(["docker", "wait", tracer], capture_output=True, timeout=remaining)
        return _copy_out(tracer, "/trace/trace"), exercise_exit
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"the observation timed out: {exc}") from exc
    finally:
        subprocess.run(["docker", "rm", "-f", "-v", subj, tracer], capture_output=True)


def _copy_out(container: str, path: str) -> str:
    r = subprocess.run(["docker", "cp", f"{container}:{path}", "-"], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"no trace in the tracer: {r.stderr.decode(errors='replace')[:300]}")
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
        member = tar.next()
        data = tar.extractfile(member) if member else None
        return data.read().decode("utf-8", "replace") if data else ""


def _docker(args: list[str], stdin: str | None = None) -> str:
    r = subprocess.run(["docker", *args], input=stdin, capture_output=True, text=True,
                       timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args[:2])} failed: {r.stderr.strip()[:800]}")
    return r.stdout
