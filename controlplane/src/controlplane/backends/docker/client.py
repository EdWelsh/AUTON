"""Parse docker intents from utterances and run the real ``docker`` CLI.

Two layers, kept separate so the parser is testable offline:

* :func:`parse_command` — pure: utterance -> :class:`DockerCommand`.
* :func:`run_docker` / :func:`handle` — shell out to the real ``docker`` binary.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum

from controlplane.core import CapabilityResult

# Words that are part of the phrasing, never an image/container reference.
_STOPWORDS = frozenset(
    {
        "docker",
        "container",
        "containers",
        "the",
        "a",
        "an",
        "for",
        "of",
        "in",
        "on",
        "with",
        "please",
        "me",
        "all",
        "image",
        "named",
        "name",
        "called",
        "id",
        "and",
        "to",
        # Action verbs — they pick the sub-command, never name the target.
        "run",
        "running",
        "start",
        "starting",
        "launch",
        "launching",
        "stop",
        "stopping",
        "kill",
        "killing",
        "log",
        "logs",
        "remove",
        "removing",
        "delete",
        "deleting",
        "rm",
        "list",
        "show",
        "ps",
        "what",
        "from",
    }
)

# Default timeout for docker subprocess calls (seconds).
_DOCKER_TIMEOUT = 60


class DockerAction(str, Enum):
    """The sub-command parsed from the utterance."""

    RUN = "run"
    LIST = "list"
    STOP = "stop"
    LOGS = "logs"
    REMOVE = "remove"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DockerCommand:
    """Structured intent parsed from a chat utterance (immutable)."""

    action: DockerAction
    target: str = ""  # image (run) or container id/name (stop/logs/rm)
    argv: tuple[str, ...] = field(default_factory=tuple)


def _candidate_tokens(text: str) -> list[str]:
    """Tokens that could be an image name or container id/name."""
    out: list[str] = []
    for raw in text.split():
        tok = raw.strip(".,!?;:\"'()")
        if not tok:
            continue
        if tok.lower() in _STOPWORDS:
            continue
        out.append(tok)
    return out


def _detect_action(low: str) -> DockerAction:
    if "log" in low:
        return DockerAction.LOGS
    if "stop" in low or "kill" in low:
        return DockerAction.STOP
    if "remove" in low or "rm " in low or low.endswith(" rm") or "delete" in low:
        return DockerAction.REMOVE
    if "run" in low or "start" in low or "launch" in low:
        return DockerAction.RUN
    if "list" in low or "ps" in low or "show" in low or "what" in low:
        return DockerAction.LIST
    return DockerAction.UNKNOWN


def parse_command(text: str) -> DockerCommand:
    """Map a natural-language utterance to a :class:`DockerCommand`.

    Pure function — no subprocess, safe to unit-test without docker installed.
    """
    low = text.lower()
    action = _detect_action(low)
    tokens = _candidate_tokens(text)

    if action is DockerAction.LIST:
        return DockerCommand(action=action, argv=("ps", "-a"))

    if action is DockerAction.UNKNOWN:
        return DockerCommand(action=action)

    target = tokens[0] if tokens else ""
    if not target:
        return DockerCommand(action=action)

    if action is DockerAction.RUN:
        argv = ("run", "-d", target)
    elif action is DockerAction.STOP:
        argv = ("stop", target)
    elif action is DockerAction.LOGS:
        argv = ("logs", "--tail", "50", target)
    elif action is DockerAction.REMOVE:
        argv = ("rm", "-f", target)
    else:  # pragma: no cover - exhaustive above
        argv = ()

    return DockerCommand(action=action, target=target, argv=argv)


def run_docker(argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    """Run ``docker <argv...>`` and capture output (real subprocess)."""
    return subprocess.run(  # noqa: S603 - fixed binary, args from parsed tokens
        ["docker", *argv],
        capture_output=True,
        text=True,
        timeout=_DOCKER_TIMEOUT,
        check=False,
    )


def handle(text: str) -> CapabilityResult:
    """Parse the utterance, run the real docker CLI, return a concise result."""
    if shutil.which("docker") is None:
        return CapabilityResult.fail(
            "docker is not installed or not on PATH",
            text="I can't reach docker — the docker CLI isn't installed here.",
        )

    cmd = parse_command(text)

    if cmd.action is DockerAction.UNKNOWN:
        return CapabilityResult.fail(
            "could not understand docker command",
            text=(
                "I didn't catch a docker action. Try 'run nginx in docker', "
                "'list containers', 'stop <id>', 'logs for <id>', or 'remove <id>'."
            ),
        )
    if not cmd.argv:
        return CapabilityResult.fail(
            "missing image or container reference",
            text=f"I need an image or container name to {cmd.action.value}.",
        )

    try:
        proc = run_docker(cmd.argv)
    except subprocess.TimeoutExpired:
        return CapabilityResult.fail(
            "docker command timed out",
            text=f"The docker {cmd.action.value} command timed out.",
        )
    except OSError as exc:  # binary vanished / exec failure
        return CapabilityResult.fail(
            f"failed to exec docker: {exc}",
            text="I couldn't run the docker CLI.",
        )

    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    if proc.returncode != 0:
        return CapabilityResult.fail(
            stderr or f"docker {cmd.action.value} exited {proc.returncode}",
            text=f"docker {cmd.action.value} failed: {stderr or '(no output)'}",
        )

    summary = stdout or f"docker {cmd.action.value} succeeded."
    return CapabilityResult.ok(
        summary,
        action=cmd.action.value,
        target=cmd.target,
        argv=list(cmd.argv),
        returncode=proc.returncode,
        stdout=stdout,
    )
