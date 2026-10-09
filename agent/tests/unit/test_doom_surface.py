"""The Doom engine's measured needs (w23 R12.1): the committed record matches a fresh measurement."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
RECORD = ROOT / "agent/kernel_spec/reference/doom-surface.yaml"
SPEC = ROOT / "agent/kernel_spec/services/play-doom.md"


def test_the_record_and_spec_agree_on_the_count_and_the_provided_file():
    rec = yaml.safe_load(RECORD.read_text())
    assert rec["count"] == sum(len(v) for v in rec["needs"].values())
    spec = SPEC.read_text()
    assert "libc_min.c" in spec and "doom-surface.yaml" in spec
    platform = [g for g in rec["needs"] if g.startswith("platform")]
    assert rec["needs"][platform[0]] == ["DG_DrawFrame", "DG_GetKey", "DG_GetTicksMs",
                                         "DG_Init", "DG_SetWindowTitle", "DG_SleepMs"]
    assert f"({rec['count']} names" in spec


@pytest.mark.skipif(not (ROOT / ".cache/third_party/doomgeneric").is_dir() or not shutil.which("clang"),
                    reason="needs the local doomgeneric clone and clang")
def test_a_fresh_measurement_reproduces_the_record():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/doom_surface.py")], capture_output=True, text=True)
    assert yaml.safe_load(r.stdout) == yaml.safe_load(RECORD.read_text())
