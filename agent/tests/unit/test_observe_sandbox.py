"""The sandbox flags are asserted, not assumed (A5, subject-trust.md).

The owner decided subject repositories are untrusted and observed only in a
sandbox. Each clause of that verdict is a flag, and each flag is checked here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from observe_sandbox import Limits, build, run_argv  # noqa: E402

ARGV = run_argv("img", ["python", "app.py"], "curl x", Limits())


def _pair(flag):
    return ARGV[ARGV.index(flag) + 1]


def test_no_network():
    assert _pair("--network") == "none"


def test_read_only_root_and_only_a_tmpfs_is_writable():
    assert "--read-only" in ARGV and _pair("--tmpfs").startswith("/tmp")


def test_every_capability_dropped_but_the_tracers():
    assert _pair("--cap-drop") == "ALL" and _pair("--cap-add") == "SYS_PTRACE"
    assert ARGV.count("--cap-add") == 1
    assert _pair("--security-opt") == "no-new-privileges"


def test_no_host_mounts_and_no_host_environment():
    assert "-v" not in ARGV and "--volume" not in ARGV and "--mount" not in ARGV
    envs = [ARGV[i + 1] for i, a in enumerate(ARGV) if a == "--env"]
    assert all(e.startswith("AUTON_") for e in envs), envs
    assert "--env-file" not in ARGV


def test_limits_are_set():
    assert _pair("--pids-limit") and _pair("--memory") and _pair("--cpus")


def test_disposable():
    assert "--rm" in ARGV


def test_a_subject_without_a_dockerfile_is_refused(tmp_path):
    with pytest.raises(RuntimeError, match="no Dockerfile and none was given"):
        build(tmp_path, "t")
