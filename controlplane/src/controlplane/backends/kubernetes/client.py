"""Parse chat utterances into ``kubectl`` commands and run the real tool.

Two concerns, kept separate so the parser is unit-testable without a cluster:

* :func:`parse` turns free-form text into an immutable :class:`KubectlPlan`
  (verb + argv), with no side effects.
* :func:`run_kubectl` / :func:`cluster_reachable` shell out to the real binary.

The parser is intentionally rule-based (mirrors the kernel's keyword roles): a
verb is chosen by the first matching trigger, then target / replicas / file are
extracted from the remaining words.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum

KUBECTL = "kubectl"
DEFAULT_TIMEOUT_S = 30
REACHABLE_TIMEOUT_S = 3

# A file argument for `apply -f`: ends in a yaml/json extension.
_FILE_RE = re.compile(r"\b([\w./-]+\.(?:ya?ml|json))\b", re.IGNORECASE)
# "scale ... to 3" / "3 replicas" / "replicas=3".
_REPLICAS_RE = re.compile(r"\b(?:to|replicas?(?:\s*=|\s+to)?)\s+(\d+)\b", re.IGNORECASE)
_REPLICAS_TRAILING_RE = re.compile(r"\b(\d+)\s+replicas?\b", re.IGNORECASE)

# Words that are verbs/prepositions/filler, never a resource name.
_STOPWORDS = frozenset(
    {
        "deploy", "deployment", "deployments", "to", "the", "cluster", "in", "k8s",
        "kubernetes", "kubectl", "scale", "delete", "remove", "rm", "logs", "log",
        "for", "of", "pod", "pods", "from", "what", "whats", "running", "is",
        "show", "list", "get", "me", "a", "an", "on", "up", "and", "please",
        "replicas", "replica", "service", "services", "namespace", "namespaces",
        "all",
    }
)


class Verb(str, Enum):
    """The kubectl sub-command a parsed utterance maps to."""

    APPLY = "apply"
    GET = "get"
    SCALE = "scale"
    DELETE = "delete"
    LOGS = "logs"


@dataclass(frozen=True)
class KubectlPlan:
    """An immutable, ready-to-run kubectl invocation parsed from text.

    ``argv`` excludes the leading ``kubectl`` binary so callers can prepend the
    resolved path. ``error`` is set (and ``argv`` empty) when an utterance matched
    a verb but lacked a required argument (e.g. scale without a number).
    """

    verb: Verb
    argv: tuple[str, ...] = field(default_factory=tuple)
    target: str | None = None
    replicas: int | None = None
    file: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.argv)


def _first_resource(text: str) -> str | None:
    """Return the first non-stopword, non-numeric token — the resource name."""
    for raw in re.split(r"[\s,]+", text.strip()):
        token = raw.strip(".:'\"()")
        if not token or token.lower() in _STOPWORDS or token.isdigit():
            continue
        if _FILE_RE.fullmatch(token):
            continue
        return token
    return None


def _parse_replicas(text: str) -> int | None:
    match = _REPLICAS_RE.search(text) or _REPLICAS_TRAILING_RE.search(text)
    return int(match.group(1)) if match else None


def parse(text: str) -> KubectlPlan:
    """Map an utterance to a :class:`KubectlPlan` (pure, no kubectl needed)."""
    lowered = text.lower()

    # apply: an explicit deploy/apply with a manifest file.
    if ("deploy" in lowered or "apply" in lowered) and (m := _FILE_RE.search(text)):
        file = m.group(1)
        return KubectlPlan(
            verb=Verb.APPLY, argv=("apply", "-f", file), file=file
        )

    # scale: needs a target and a replica count.
    if "scale" in lowered:
        target = _first_resource(text)
        replicas = _parse_replicas(text)
        if not target:
            return KubectlPlan(Verb.SCALE, error="scale: no deployment named")
        if replicas is None:
            return KubectlPlan(
                Verb.SCALE, target=target, error="scale: no replica count given"
            )
        return KubectlPlan(
            verb=Verb.SCALE,
            argv=("scale", f"deployment/{target}", f"--replicas={replicas}"),
            target=target,
            replicas=replicas,
        )

    # logs: needs a pod name.
    if "log" in lowered:
        target = _first_resource(text)
        if not target:
            return KubectlPlan(Verb.LOGS, error="logs: no pod named")
        return KubectlPlan(
            verb=Verb.LOGS, argv=("logs", target), target=target
        )

    # delete: needs a target; default resource type is deployment.
    if any(w in lowered for w in ("delete", "remove")):
        target = _first_resource(text)
        if not target:
            return KubectlPlan(Verb.DELETE, error="delete: no resource named")
        kind = "pod" if "pod" in lowered else "deployment"
        return KubectlPlan(
            verb=Verb.DELETE,
            argv=("delete", kind, target),
            target=target,
        )

    # get / list / "what's running": default read.
    resource = "pods"
    if "deploy" in lowered:
        resource = "deployments"
    elif "service" in lowered or "svc" in lowered:
        resource = "services"
    elif "namespace" in lowered or "ns " in lowered:
        resource = "namespaces"
    return KubectlPlan(verb=Verb.GET, argv=("get", resource))


def kubectl_path() -> str | None:
    """Absolute path to the real ``kubectl`` binary, or ``None`` if absent."""
    return shutil.which(KUBECTL)


def cluster_reachable(timeout_s: int = REACHABLE_TIMEOUT_S) -> bool:
    """True only if kubectl exists AND a cluster answers within ``timeout_s``."""
    binary = kubectl_path()
    if binary is None:
        return False
    try:
        completed = subprocess.run(  # noqa: S603 - fixed binary, no shell
            [binary, "version", f"--request-timeout={timeout_s}s"],
            capture_output=True,
            text=True,
            timeout=timeout_s + 2,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return completed.returncode == 0


def run_kubectl(
    argv: tuple[str, ...], timeout_s: int = DEFAULT_TIMEOUT_S
) -> subprocess.CompletedProcess[str]:
    """Run ``kubectl <argv>`` against the active context and capture output.

    Raises ``FileNotFoundError`` if kubectl is not installed so the handler can
    surface a clear message instead of a stack trace.
    """
    binary = kubectl_path()
    if binary is None:
        raise FileNotFoundError("kubectl not found on PATH")
    return subprocess.run(  # noqa: S603 - fixed binary, parsed argv, no shell
        [binary, *argv],
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
