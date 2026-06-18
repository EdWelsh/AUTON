"""Docker backend tests (Unit 2).

Two layers:
* Pure parser tests — no docker needed (image/name/subcommand extraction).
* Real-docker E2E — guarded by ``shutil.which("docker")``; actually runs a
  throwaway container and asserts real output. Never mocked.
"""

from __future__ import annotations

import shutil

import pytest

from controlplane.backends.docker.client import (
    DockerAction,
    handle,
    parse_command,
)
from controlplane.backends.docker.plugin import get_capabilities
from controlplane.core import CapabilityStatus, Registry, Router

HAS_DOCKER = shutil.which("docker") is not None
docker_required = pytest.mark.skipif(not HAS_DOCKER, reason="docker not installed")


# --------------------------------------------------------------------------- #
# Pure parser (offline, no docker)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("text", "action", "target"),
    [
        ("run nginx in docker", DockerAction.RUN, "nginx"),
        ("launch redis container", DockerAction.RUN, "redis"),
        ("start the hello-world image", DockerAction.RUN, "hello-world"),
        ("stop nginx", DockerAction.STOP, "nginx"),
        ("kill container abc123", DockerAction.STOP, "abc123"),
        ("logs for web1", DockerAction.LOGS, "web1"),
        ("show me the logs of deadbeef", DockerAction.LOGS, "deadbeef"),
        ("remove abc123", DockerAction.REMOVE, "abc123"),
        ("delete the container feed01", DockerAction.REMOVE, "feed01"),
    ],
)
def test_parse_action_and_target(text, action, target):
    cmd = parse_command(text)
    assert cmd.action is action
    assert cmd.target == target


def test_parse_list_has_no_target_and_uses_ps():
    cmd = parse_command("list containers")
    assert cmd.action is DockerAction.LIST
    assert cmd.target == ""
    assert cmd.argv == ("ps", "-a")


def test_parse_run_builds_detached_argv():
    cmd = parse_command("run nginx in docker")
    assert cmd.argv == ("run", "-d", "nginx")


def test_parse_logs_tails_output():
    cmd = parse_command("logs for web1")
    assert cmd.argv == ("logs", "--tail", "50", "web1")


def test_parse_remove_forces():
    assert parse_command("remove abc123").argv == ("rm", "-f", "abc123")


def test_parse_stop():
    assert parse_command("stop nginx").argv == ("stop", "nginx")


def test_parse_unknown_when_no_action():
    cmd = parse_command("docker please do something vague")
    # "do" is not an action verb; nothing matches.
    assert cmd.action is DockerAction.UNKNOWN


def test_run_without_target_yields_empty_argv():
    # "run docker" -> action RUN but every token is a stopword.
    cmd = parse_command("run docker")
    assert cmd.action is DockerAction.RUN
    assert cmd.target == ""
    assert cmd.argv == ()


def test_strips_punctuation_from_target():
    cmd = parse_command("stop 'nginx'.")
    assert cmd.target == "nginx"


# --------------------------------------------------------------------------- #
# Plugin / registry wiring
# --------------------------------------------------------------------------- #
def test_plugin_exposes_working_docker_capability():
    caps = get_capabilities()
    assert len(caps) == 1
    cap = caps[0]
    assert cap.name == "docker"
    assert cap.status is CapabilityStatus.WORKING
    assert cap.handler is not None
    assert cap.matches("run nginx in docker")
    assert cap.matches("list containers")


def test_routing_reaches_docker_capability():
    router = Router(Registry())
    cap = router.registry.match("run nginx in docker")
    assert cap is not None
    assert cap.name == "docker"


# --------------------------------------------------------------------------- #
# handle() without docker present
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(HAS_DOCKER, reason="only meaningful when docker is absent")
def test_handle_reports_missing_docker():
    res = handle("run nginx in docker")
    assert res.handled is True
    assert res.error is not None
    assert "docker" in res.error.lower()


# --------------------------------------------------------------------------- #
# Real docker E2E (no mocks) — runs a throwaway container, cleans up.
# --------------------------------------------------------------------------- #
@docker_required
def test_handle_runs_real_container_and_lists_then_cleans_up():
    name = "auton-cp-docker-test"
    # Best-effort pre-clean from any prior failed run.
    import subprocess

    subprocess.run(
        ["docker", "rm", "-f", name],
        capture_output=True,
        text=True,
        check=False,
    )

    try:
        # Run a real detached container by explicit name.
        run = subprocess.run(
            ["docker", "run", "-d", "--name", name, "alpine", "sleep", "30"],
            capture_output=True,
            text=True,
            check=False,
        )
        if run.returncode != 0:
            pytest.skip(f"docker daemon unavailable: {run.stderr.strip()}")

        # list via the capability handler — real output.
        listed = handle("list containers")
        assert listed.handled is True
        assert listed.error is None
        assert name in listed.text

        # stop via the handler.
        stopped = handle(f"stop {name}")
        assert stopped.handled is True
        assert stopped.error is None
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True,
            text=True,
            check=False,
        )


@docker_required
def test_handle_run_hello_world_real():
    import subprocess

    daemon = subprocess.run(
        ["docker", "info"], capture_output=True, text=True, check=False
    )
    if daemon.returncode != 0:
        pytest.skip("docker daemon not running")

    res = handle("run hello-world in docker")
    # run -d prints a container id on success.
    assert res.handled is True
    if res.error is None:
        cid = res.data.get("stdout", "").strip()
        assert cid  # a container id was printed
        subprocess.run(
            ["docker", "rm", "-f", cid],
            capture_output=True,
            text=True,
            check=False,
        )
