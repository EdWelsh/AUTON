"""A packaged application, booted as a virtual machine and graded from outside (w23 C3).

Slow under software emulation (minutes); skipped when Docker is not running. The
fixture is the same flask app and operator probe the container substrate is graded on.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from app_probe import EXIT_FAILED, EXIT_WORKED, load_probe  # noqa: E402
from vm_probe import probe_vm  # noqa: E402

SUBJECT = ROOT / "agent" / "tests" / "fixtures" / "apps" / "flask-hello"
PROBE = ROOT / "agent" / "tests" / "fixtures" / "probes" / "flask-hello.yaml"

pytestmark = pytest.mark.skipif(
    not shutil.which("docker")
    or subprocess.run(["docker", "info"], capture_output=True).returncode != 0,
    reason="needs Docker")


def _build(tag: str, extra_remove: str = "") -> str:
    df = SUBJECT / "Dockerfile"
    if not df.is_file():
        pytest.skip("fixture has no Dockerfile")
    r = subprocess.run(["docker", "build", "-q", "-t", tag, str(SUBJECT)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return tag


def test_the_fixture_works_as_a_vm_and_a_broken_one_fails():
    spec = load_probe(PROBE)
    assert probe_vm(_build("auton-vm-test-ok"), spec).code == EXIT_WORKED
    broken = dict(spec, checks=[dict(spec["checks"][0], expect_body_contains="not-in-the-body")],
                  vm_start_timeout_s=60)
    assert probe_vm("auton-vm-test-ok", broken).code == EXIT_FAILED


def test_an_unknown_substrate_has_no_prober():
    from ablate import _prober
    assert _prober("vm") is probe_vm
    with pytest.raises(Exception, match="no probe for substrate"):
        _prober("lxc")
