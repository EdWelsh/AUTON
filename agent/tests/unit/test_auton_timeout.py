"""auton_timeout must not hold the caller's pipe open after the command exits.

Its killer subshell's `sleep` survives the subshell being killed; with the
caller's stdout inherited, `auton_timeout 3600 cmd | tee log` waited the full
hour for EOF after cmd finished (seen in the w13 F6 run).
"""

import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_pipeline_ends_when_the_command_does():
    script = (f'source "{ROOT}/scripts/lib/toolchain.sh"; TIMEOUT_BIN=; '
              'auton_timeout 20 echo hi | cat')
    t0 = time.monotonic()
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == "hi"
    assert time.monotonic() - t0 < 5
