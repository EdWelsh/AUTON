"""The sandbox flags are asserted, not assumed (A5, subject-trust.md).

The owner decided subject repositories are untrusted and observed only in a
sandbox. Each clause of that verdict is a flag, checked here — and, after the
w18 review found the subject could forge its own trace, so is the separation
between the subject and the tracer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from observe_sandbox import (  # noqa: E402
    SUBJECT_USER,
    Limits,
    build,
    subject_argv,
    tracer_argv,
)

SUBJECT = subject_argv("s", "img", ["python", "app.py"], Limits())
TRACER = tracer_argv("t", "s", Limits())


def _pair(argv, flag):
    return argv[argv.index(flag) + 1]


def test_no_network_for_either():
    assert _pair(SUBJECT, "--network") == "none" and _pair(TRACER, "--network") == "none"


def test_the_subject_holds_no_capability_and_no_root():
    assert _pair(SUBJECT, "--cap-drop") == "ALL" and "--cap-add" not in SUBJECT
    assert _pair(SUBJECT, "--user") == SUBJECT_USER and not SUBJECT_USER.startswith("0")


def test_only_the_tracer_can_trace_and_it_joins_from_outside():
    assert _pair(TRACER, "--cap-drop") == "ALL" and _pair(TRACER, "--cap-add") == "SYS_PTRACE"
    assert TRACER.count("--cap-add") == 1
    assert _pair(TRACER, "--pid") == "container:s"


def test_read_only_root_and_only_a_tmpfs_is_writable():
    assert "--read-only" in SUBJECT and _pair(SUBJECT, "--tmpfs").startswith("/tmp")


def test_no_new_privileges_and_limits():
    for argv in (SUBJECT, TRACER):
        assert _pair(argv, "--security-opt") == "no-new-privileges"
        assert _pair(argv, "--pids-limit") and _pair(argv, "--memory")
    assert _pair(SUBJECT, "--cpus")


def test_no_host_mounts_and_no_host_environment():
    for argv in (SUBJECT, TRACER):
        for flag in ("-v", "--volume", "--mount", "--env", "-e", "--env-file"):
            assert flag not in argv, flag


def test_the_gate_shell_is_our_instrumentation_not_the_images():
    from observe_sandbox import SHELL
    assert _pair(SUBJECT, "--entrypoint") == SHELL


def test_the_command_is_argv_not_a_shell_string():
    assert SUBJECT[-2:] == ["python", "app.py"]


def test_a_subject_without_a_dockerfile_is_refused(tmp_path):
    with pytest.raises(RuntimeError, match="no Dockerfile and none was given"):
        build(tmp_path, "t")
