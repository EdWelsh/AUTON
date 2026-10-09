"""Linux hosts inside Docker/Rancher stand in for HOST-MATRIX rows until real machines exist.

What they prove is the toolchain and boot path on that distro and architecture. What they
cannot prove is silicon: the amd64 host is an emulated CPU, and the conformance harness must
say SKIPPED there rather than publish the emulator's answer.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "scripts" / "host-run.sh"

pytestmark = pytest.mark.skipif(
    not shutil.which("docker")
    or subprocess.run(["docker", "info"], capture_output=True).returncode != 0,
    reason="needs Docker")


def _run(arch, cmd, timeout=1500):
    return subprocess.run([str(RUN), arch, cmd], capture_output=True, text=True, timeout=timeout)


def test_linux_arm64_builds_and_boots_the_aarch64_smoke_image():
    r = _run("arm64", "tests/kernel/run_aarch64_smoke.sh")
    assert r.returncode == 0, r.stdout[-800:]
    assert "aarch64 scaffolding: PASS" in r.stdout


def test_linux_amd64_passes_preflight_and_flags_itself_emulated():
    r = _run("amd64", "scripts/preflight.sh")
    assert "ALL PASS" in r.stdout, r.stdout[-800:]


def test_conformance_refuses_to_publish_an_emulators_answer():
    r = _run("amd64", "tests/conformance/run_conformance.sh")
    assert r.returncode == 0, r.stdout[-800:]
    assert "SKIPPED on this host" in r.stdout
