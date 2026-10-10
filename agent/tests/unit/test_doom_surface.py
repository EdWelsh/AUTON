"""The Doom engine's measured needs (w23 R12.1): the record and the spec agree."""
from pathlib import Path

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

