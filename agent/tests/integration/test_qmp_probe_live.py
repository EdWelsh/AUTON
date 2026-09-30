"""The Doom probe against a real QEMU guest, before any Doom image exists (R12).

GRUB's menu is a real framebuffer guest that animates by itself (the countdown)
and answers Escape (the countdown line disappears). The probe must call that
WORKED with Escape, and must NOT call it WORKED with no key sent.

This is where the macOS screendump "crash" was characterised: it was a full
disk, not the platform. And it calibrated MIN_EXTRA: a 1% floor called GRUB's
real 0.5% response inconclusive.

Needs qemu-system-x86_64 and the kernel toolchain (scripts/lib/toolchain.sh);
skipped, with the reason, without them.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PY = sys.executable


def _tools() -> str | None:
    for tool in ("qemu-system-x86_64", "make"):
        if not shutil.which(tool):
            return f"no {tool}"
    if not (shutil.which("i686-elf-grub-mkrescue") or shutil.which("grub-mkrescue")):
        return "no grub-mkrescue"
    return None


pytestmark = pytest.mark.skipif(_tools() is not None, reason=str(_tools()))


@pytest.fixture(scope="module")
def menu_iso():
    work = Path(tempfile.mkdtemp(prefix="qmpl", dir="/tmp"))
    tree = work / "tree"
    subprocess.run(["bash", str(ROOT / "scripts/kernel-base.sh"), str(tree)], check=True,
                   capture_output=True)
    subprocess.run(["bash", "-c", f'source "{ROOT}/scripts/lib/toolchain.sh"; make -C "{tree}" iso'],
                   check=True, capture_output=True)
    cfg = tree / "build/isodir/boot/grub/grub.cfg"
    cfg.write_text(cfg.read_text().replace("set timeout=0", "set timeout=30"))
    mkrescue = shutil.which("i686-elf-grub-mkrescue") or shutil.which("grub-mkrescue")
    iso = work / "menu.iso"
    subprocess.run([mkrescue, "-o", str(iso), str(tree / "build/isodir")], check=True,
                   capture_output=True)
    yield work, iso
    shutil.rmtree(work, ignore_errors=True)


def _probe(work: Path, iso: Path, keys: str) -> subprocess.CompletedProcess:
    sock = work / "q.sock"
    sock.unlink(missing_ok=True)
    qemu = subprocess.Popen(["qemu-system-x86_64", "-cdrom", str(iso), "-m", "256", "-vga", "std",
                             "-display", "none", "-qmp", f"unix:{sock},server,nowait",
                             "-serial", "null"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(6)
        return subprocess.run([PY, str(ROOT / "scripts/qmp_probe.py"), str(sock), str(work)],
                              capture_output=True, text=True, timeout=120,
                              env={**os.environ, "QMP_PROBE_KEYS": keys})
    finally:
        qemu.kill()
        qemu.wait()


def test_a_real_guest_that_answers_escape_worked(menu_iso):
    r = _probe(*menu_iso, keys="esc")
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_same_guest_with_no_input_is_not_worked(menu_iso):
    r = _probe(*menu_iso, keys="")
    assert r.returncode in (3, 4), r.stdout
