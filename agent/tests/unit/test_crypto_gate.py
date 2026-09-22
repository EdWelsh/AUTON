"""The F12 crypto gate's record keeps its own rules (kernel_spec/decisions/ssh-crypto.md).

The gate itself is `tests/crypto/run_crypto_gate.sh`, which needs the sources in
the gitignored cache. These check what the repo carries: that the verdict names
every primitive with a source, that each source is inventoried with a licence
`licences.yaml` permits, and that no primitive was written here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

RECORD = ROOT / "agent" / "kernel_spec" / "decisions" / "ssh-crypto.md"
LICENCES = ROOT / "agent" / "kernel_spec" / "drivers" / "licences.yaml"
PRIMITIVES = ("X25519", "Ed25519", "SHA-256", "SHA-512", "ChaCha20", "Poly1305")


def test_the_verdict_covers_every_primitive():
    text = RECORD.read_text()
    assert "# Verdict: **GO**" in text or "# Verdict: **CUT**" in text
    for p in PRIMITIVES:
        assert p in text, f"{p} has no row in the verdict"


def test_the_criteria_precede_the_verdict():
    """The pass criteria were committed before the spike; in the file they must
    also stand above the verdict, unedited by it."""
    text = RECORD.read_text()
    assert text.index("## Pass criteria") < text.index("# Verdict")
    assert "nothing above this line changes" in text


def test_every_cited_source_is_inventoried_with_a_permitted_licence():
    from vendor_inventory import load

    crypto = [v for v in load() if v.category == "crypto-source"]
    assert {v.vendor for v in crypto} == {"monocypher", "bearssl"}
    table = yaml.safe_load(LICENCES.read_text())["licences"]
    for v in crypto:
        for d in v.documents:
            for name in str(d.licence or "").split(" OR "):
                entry = table.get(name.strip())
                assert entry, f"{v.vendor}: licence {name!r} is not in licences.yaml"
                assert entry["port"] == "permitted", f"{v.vendor}: {name} does not permit port"
                assert entry["depends_on_use"] is False, f"{v.vendor}: {name} routes to a human"


def test_no_primitive_is_implemented_in_this_repo():
    """The gate's rule: reuse or port, never synthesize. The harness may only
    call the sources; a primitive's own arithmetic must not appear here."""
    harness = (ROOT / "tests" / "crypto" / "vectors.c").read_text()
    for banned in ("0x61707865", "quarterround", "poly1305_blocks", "fe25519"):
        assert banned not in harness.lower(), f"{banned}: a primitive written into the harness"


@pytest.mark.skipif(not (ROOT / ".cache" / "vendor" / "crypto").is_dir(),
                    reason="sources absent: tests/crypto/fetch_sources.sh")
def test_the_gate_script_runs_when_the_sources_are_present():
    import subprocess

    r = subprocess.run(["bash", str(ROOT / "tests" / "crypto" / "run_crypto_gate.sh")],
                       capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    assert "vectors: PASS" in r.stdout
