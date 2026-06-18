"""Kubernetes capability plugin — discovered at runtime by the registry."""

from __future__ import annotations

import subprocess

from controlplane.core import Capability, CapabilityResult, CapabilityStatus

from .client import KubectlPlan, parse, run_kubectl

NAME = "kubernetes"
KEYWORDS = ("k8s", "kubernetes", "cluster", "kubectl", "deploy to")
NOTE = "drive a real cluster: apply manifests, get pods, scale, delete, logs"

_MAX_OUTPUT_CHARS = 4000


def _summarize(plan: KubectlPlan, completed: subprocess.CompletedProcess[str]) -> str:
    cmd = "kubectl " + " ".join(plan.argv)
    body = (completed.stdout or completed.stderr or "").strip()
    if len(body) > _MAX_OUTPUT_CHARS:
        body = body[:_MAX_OUTPUT_CHARS] + "\n… (truncated)"
    header = f"$ {cmd}"
    return f"{header}\n{body}" if body else header


def handle(text: str) -> CapabilityResult:
    """Parse the utterance and run the real kubectl command."""
    plan = parse(text)
    if not plan.ok:
        return CapabilityResult.fail(
            plan.error or "could not understand that kubectl request",
            text="I couldn't parse that. Try 'deploy app.yaml to the cluster', "
            "'what's running in k8s', 'scale web to 3', 'delete deployment api', "
            "or 'logs for pod nginx'.",
        )

    try:
        completed = run_kubectl(plan.argv)
    except FileNotFoundError:
        return CapabilityResult.fail(
            "kubectl is not installed",
            text="kubectl was not found on PATH — install it and point it at a "
            "cluster (kubeconfig) to use Kubernetes from chat.",
        )
    except subprocess.TimeoutExpired:
        return CapabilityResult.fail(
            "kubectl timed out",
            text="The cluster did not respond in time. Is the context reachable?",
        )

    summary = _summarize(plan, completed)
    if completed.returncode != 0:
        return CapabilityResult.fail(
            f"kubectl {plan.verb.value} failed (exit {completed.returncode})",
            text=summary,
        )
    return CapabilityResult.ok(
        summary,
        verb=plan.verb.value,
        target=plan.target,
        replicas=plan.replicas,
        file=plan.file,
        returncode=completed.returncode,
    )


def get_capabilities() -> list[Capability]:
    return [
        Capability(
            name=NAME,
            keywords=KEYWORDS,
            status=CapabilityStatus.WORKING,
            note=NOTE,
            handler=handle,
        )
    ]
