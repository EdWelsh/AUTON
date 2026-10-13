"""w25 A3: a driver that includes the x86_64 io.h builds on the host through the shim."""
import shutil
import subprocess
from pathlib import Path

import pytest

SHIM = Path(__file__).resolve().parents[3] / "tests/kernel/host_io_shim.h"
REAL_IO_H = """#ifndef AUTON_ARCH_IO_H
#define AUTON_ARCH_IO_H
#include <stdint.h>
static inline uint32_t io_read32(uint16_t port) {
    uint32_t v; __asm__ volatile("inl %1, %0" : "=a"(v) : "Nd"(port)); return v; }
#endif
"""


@pytest.mark.skipif(not shutil.which("clang"), reason="needs clang")
def test_driver_including_real_io_h_builds_with_the_shim(tmp_path):
    (tmp_path / "io.h").write_text(REAL_IO_H)
    (tmp_path / "drv.c").write_text(
        '#include "io.h"\nint main(void){ io_write32(0x10, 7); return io_read32(0x10) == 7 ? 0 : 1; }\n')
    out = tmp_path / "drv"
    cmd = ["clang", "-arch", "arm64"] if shutil.which("uname") and \
        subprocess.run(["uname", "-m"], capture_output=True, text=True).stdout.strip() == "arm64" else ["clang"]
    r = subprocess.run([*cmd, "-include", str(SHIM), str(tmp_path / "drv.c"), "-o", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert subprocess.run([str(out)]).returncode == 0
