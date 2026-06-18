"""Kubernetes backend tests (Unit 3).

Three layers:

* Pure utterance parsing — fully tested without kubectl (verb/target/replicas/file).
* Capability wiring — discovery, keywords, routing reach the k8s capability.
* Real e2e — only when kubectl AND a reachable cluster exist; never mocked,
  skipped otherwise.
"""

from __future__ import annotations

import dataclasses

import pytest

from controlplane.backends.kubernetes import client
from controlplane.backends.kubernetes.client import (
    KubectlPlan,
    Verb,
    cluster_reachable,
    kubectl_path,
    parse,
)
from controlplane.backends.kubernetes.plugin import get_capabilities, handle
from controlplane.core import CapabilityStatus, Registry, Router


# --- Pure parsing -----------------------------------------------------------

def test_parse_deploy_extracts_apply_and_file():
    plan = parse("deploy app.yaml to the cluster")
    assert plan.verb is Verb.APPLY
    assert plan.file == "app.yaml"
    assert plan.argv == ("apply", "-f", "app.yaml")
    assert plan.ok


def test_parse_apply_handles_paths_and_yml_extension():
    plan = parse("apply manifests/prod/web.yml to k8s")
    assert plan.verb is Verb.APPLY
    assert plan.file == "manifests/prod/web.yml"
    assert plan.argv == ("apply", "-f", "manifests/prod/web.yml")


def test_parse_get_default_is_pods():
    plan = parse("what's running in k8s")
    assert plan.verb is Verb.GET
    assert plan.argv == ("get", "pods")


def test_parse_get_deployments_when_mentioned():
    assert parse("list deployments in the cluster").argv == ("get", "deployments")


def test_parse_get_services():
    assert parse("show me the services in k8s").argv == ("get", "services")


def test_parse_scale_extracts_target_and_replicas():
    plan = parse("scale web to 3")
    assert plan.verb is Verb.SCALE
    assert plan.target == "web"
    assert plan.replicas == 3
    assert plan.argv == ("scale", "deployment/web", "--replicas=3")


def test_parse_scale_trailing_replicas_phrasing():
    plan = parse("scale api deployment 5 replicas")
    assert plan.target == "api"
    assert plan.replicas == 5


def test_parse_scale_without_count_is_error():
    plan = parse("scale web")
    assert plan.verb is Verb.SCALE
    assert not plan.ok
    assert plan.error is not None


def test_parse_delete_defaults_to_deployment():
    plan = parse("delete deployment api")
    assert plan.verb is Verb.DELETE
    assert plan.target == "api"
    assert plan.argv == ("delete", "deployment", "api")


def test_parse_delete_pod_uses_pod_kind():
    plan = parse("delete pod nginx-123")
    assert plan.argv == ("delete", "pod", "nginx-123")


def test_parse_logs_extracts_pod_name():
    plan = parse("logs for pod nginx")
    assert plan.verb is Verb.LOGS
    assert plan.target == "nginx"
    assert plan.argv == ("logs", "nginx")


def test_parse_logs_without_target_is_error():
    plan = parse("logs for pod")
    assert not plan.ok


def test_kubectl_plan_is_frozen():
    plan = parse("what's running in k8s")
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.verb = Verb.DELETE  # type: ignore[misc]


# --- Capability wiring ------------------------------------------------------

def test_capability_is_working_with_handler():
    (cap,) = get_capabilities()
    assert cap.name == "kubernetes"
    assert cap.status is CapabilityStatus.WORKING
    assert cap.handler is not None


def test_capability_keywords_match_common_utterances():
    (cap,) = get_capabilities()
    for utterance in (
        "deploy app.yaml to the cluster",
        "what's running in k8s",
        "scale web in kubernetes to 3",
        "run kubectl get pods",
    ):
        assert cap.matches(utterance), utterance


def test_registry_discovers_kubernetes_backend():
    names = [c.name for c in Registry().capabilities]
    assert "kubernetes" in names


def test_router_reaches_kubernetes_capability(monkeypatch):
    # Route without touching a real cluster: stub the runner.
    sentinel = {}

    class _Completed:
        returncode = 0
        stdout = "NAME   READY\nweb    1/1\n"
        stderr = ""

    def fake_run(argv, timeout_s=30):
        sentinel["argv"] = argv
        return _Completed()

    monkeypatch.setattr(
        "controlplane.backends.kubernetes.plugin.run_kubectl", fake_run
    )
    res = Router(Registry()).route("deploy app.yaml to the cluster")
    assert res.handled
    assert sentinel["argv"] == ("apply", "-f", "app.yaml")


def test_handle_reports_missing_kubectl(monkeypatch):
    def boom(argv, timeout_s=30):
        raise FileNotFoundError("kubectl not found on PATH")

    monkeypatch.setattr(
        "controlplane.backends.kubernetes.plugin.run_kubectl", boom
    )
    res = handle("what's running in k8s")
    assert res.handled and res.error == "kubectl is not installed"


def test_handle_surfaces_nonzero_exit(monkeypatch):
    class _Failed:
        returncode = 1
        stdout = ""
        stderr = 'Error from server (NotFound): deployments.apps "x" not found'

    monkeypatch.setattr(
        "controlplane.backends.kubernetes.plugin.run_kubectl",
        lambda argv, timeout_s=30: _Failed(),
    )
    res = handle("delete deployment x")
    assert res.handled and res.error is not None and "NotFound" in res.text


def test_handle_unparseable_request_fails_cleanly(monkeypatch):
    # scale with no count never reaches kubectl.
    called = {"ran": False}

    def fake_run(argv, timeout_s=30):
        called["ran"] = True

    monkeypatch.setattr(
        "controlplane.backends.kubernetes.plugin.run_kubectl", fake_run
    )
    res = handle("scale web in the cluster")
    assert res.handled and res.error is not None
    assert called["ran"] is False


# --- Real e2e (no mocks) ----------------------------------------------------

_HAVE_CLUSTER = kubectl_path() is not None and cluster_reachable()


@pytest.mark.skipif(
    not _HAVE_CLUSTER, reason="kubectl or a reachable cluster is absent"
)
def test_e2e_get_namespaces_against_real_cluster():
    completed = client.run_kubectl(("get", "ns"))
    assert completed.returncode == 0
    assert "NAME" in completed.stdout or completed.stdout.strip()


@pytest.mark.skipif(
    not _HAVE_CLUSTER, reason="kubectl or a reachable cluster is absent"
)
def test_e2e_handle_get_pods_through_capability():
    res = handle("what's running in k8s")
    assert res.handled and res.error is None
    assert res.data["verb"] == "get"
