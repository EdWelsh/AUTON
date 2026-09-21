"""Accelerator selection in scripts/lib/toolchain.sh.

`auton_accel_select` is a pure function of (uname -s, what the QEMU binary
lists, whether /dev/kvm is usable), so the Linux and Windows branches are
checked here from any host. Exercising them on real hosts is a separate claim,
and docs/HOST-MATRIX.md says per row whether it has been made.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

TOOLCHAIN = Path(__file__).resolve().parents[3] / "scripts" / "lib" / "toolchain.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _bash(script: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", f'source "{TOOLCHAIN}"; {script}'],
        capture_output=True,
        text=True,
        env=env,
    )


def _select(os_name: str, listed: str, kvm_ok: int) -> tuple[int, str]:
    result = _bash(f'auton_accel_select "{os_name}" "{listed}" {kvm_ok}')
    return result.returncode, result.stdout.split(" ", 1)[0]


@pytest.mark.parametrize(
    ("os_name", "listed", "kvm_ok", "expected"),
    [
        ("Linux", "kvm tcg", 1, "kvm"),
        # Listed by the binary is not permitted by the host.
        ("Linux", "kvm tcg", 0, "tcg"),
        ("Darwin", "hvf tcg", 0, "hvf"),
        # An arm64 Mac's qemu-system-x86_64 lists only tcg: HVF cannot run a foreign-arch guest.
        ("Darwin", "tcg", 0, "tcg"),
        ("MINGW64_NT-10.0", "whpx tcg", 0, "whpx"),
        ("MINGW64_NT-10.0", "tcg", 0, "tcg"),
        ("FreeBSD", "tcg", 0, "tcg"),
    ],
)
def test_selects_best_available(os_name, listed, kvm_ok, expected):
    assert _select(os_name, listed, kvm_ok) == (0, expected)


def test_tcg_fallback_says_why():
    out = _bash('auton_accel_select Linux "kvm tcg" 0').stdout
    assert out.startswith("tcg ") and "kvm device usable: 0" in out


def test_nothing_usable_is_an_error_not_a_guess():
    assert _select("Darwin", "", 0)[0] != 0


def _qemu_stub(tmp_path: Path, accels: str) -> str:
    stub = tmp_path / "qemu"
    lines = "\n".join(accels.split())
    header = "Accelerators supported in QEMU binary:"
    stub.write_text(f'#!/usr/bin/env bash\nprintf "{header}\\n{lines}\\n"\n')
    stub.chmod(0o755)
    return str(stub)


def test_explicit_unavailable_request_fails_loudly(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "QEMU": _qemu_stub(tmp_path, "tcg")}
    result = _bash("auton_accel kvm", env)
    assert result.returncode != 0
    assert "lists: tcg" in result.stderr


def test_environment_request_is_honoured(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "QEMU": _qemu_stub(tmp_path, "kvm tcg"), "AUTON_ACCEL": "tcg"}
    result = _bash('auton_accel && echo "$AUTON_ACCEL|$AUTON_ACCEL_REASON"', env)
    assert result.stdout.strip() == "tcg|requested explicitly"


def test_argument_beats_environment(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "QEMU": _qemu_stub(tmp_path, "whpx tcg"), "AUTON_ACCEL": "whpx"}
    result = _bash('auton_accel tcg && echo "$AUTON_ACCEL"', env)
    assert result.stdout.strip() == "tcg"
