"""The agreed kernel base, and why it is not the reference tag.

w11 seeded F6 from kernel-reference-v1. It predates F4's static-IP setup.c, so
a TFTP service was refused at link closure over `dhcp_run`, a refusal no agent
could have avoided. kernel-base-v2 carries F4's hooks; an empty service on it
fails only for the service's own missing entry point.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from build_service import GateFailure, build  # noqa: E402

SCRIPT = ROOT / "scripts" / "kernel-base.sh"
CC = os.environ.get("CC", "x86_64-elf-gcc")


def _has_tag(tag: str) -> bool:
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "-q", "--verify",
                           f"refs/tags/{tag}"], capture_output=True).returncode == 0


needs_bases = pytest.mark.skipif(
    not all(_has_tag(t) for t in ("kernel-base-v3", "kernel-base-v2", "kernel-reference-v1")),
    reason="base tags absent (shallow clone): git fetch --tags")
needs_cc = pytest.mark.skipif(shutil.which(CC) is None, reason=f"{CC} not installed")


def _extract(tmp_path: Path, rev: str) -> Path:
    tree = tmp_path / rev
    r = subprocess.run(["bash", str(SCRIPT), str(tree), "--rev", rev],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return tree


@needs_bases
def test_the_script_refuses_a_non_empty_directory(tmp_path):
    (tmp_path / "x").write_text("keep me")
    r = subprocess.run(["bash", str(SCRIPT), str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 2 and "not empty" in r.stderr
    assert (tmp_path / "x").read_text() == "keep me"


def test_an_absent_tag_is_named_not_substituted(tmp_path):
    r = subprocess.run(["bash", str(SCRIPT), str(tmp_path / "t"), "--rev", "no-such-base"],
                       capture_output=True, text=True)
    assert r.returncode == 2 and "git fetch --tags" in r.stderr


@needs_bases
def test_v2_differs_from_v1_by_exactly_f4s_hooks():
    out = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only",
                          "kernel-reference-v1", "kernel-base-v2", "--", "kernels/x86_64"],
                         capture_output=True, text=True).stdout.split()
    assert sorted(out) == ["kernels/x86_64/kernel/boot/kernel_main.c",
                           "kernels/x86_64/kernel/net/setup.c"]


@needs_bases
@needs_cc
def test_an_empty_service_on_the_default_base_fails_only_for_its_own_entry(tmp_path):
    tree = _extract(tmp_path, "kernel-base-v3")
    with pytest.raises(GateFailure) as exc:
        build("tftp", tree, cc=CC)
    assert "tftp_serve" in str(exc.value)
    assert "link closure" not in str(exc.value)


@needs_bases
@needs_cc
def test_v1_fails_at_link_closure_which_is_why_v2_exists(tmp_path):
    tree = _extract(tmp_path, "kernel-reference-v1")
    with pytest.raises(GateFailure, match="link closure"):
        build("tftp", tree, cc=CC)


@needs_bases
def test_no_mapped_capability_is_phantom_against_the_base(tmp_path):
    """A mapping to files that do not exist turns a refusal into a silent
    omission (source_map.yaml's header). vmm and slab were phantom until w12
    removed them; this keeps every remaining mapping honest against the base."""
    from build_manifest import SourceMap, resolve

    tree = _extract(tmp_path, "kernel-base-v3")
    caps = sorted(SourceMap.load().capabilities)
    _, _, info = resolve(caps, [], tree)

    assert info.get("phantom_capabilities") == []


@needs_bases
def test_v3_differs_from_v2_by_exactly_the_loader():
    out = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only",
                          "kernel-base-v2", "kernel-base-v3", "--", "kernels/x86_64"],
                         capture_output=True, text=True).stdout.split()
    assert sorted(out) == ["kernels/x86_64/kernel/include/neural.h",
                           "kernels/x86_64/kernel/slm/neural/neural_backend.c"]


@needs_bases
def test_the_base_loads_the_format_the_exporter_writes():
    """The failure that made v3: the exporter wrote v3 from w10 on and the base
    required v2, so parity failed with LOAD FAIL on every e2e run."""
    import re
    sys.path.insert(0, str(ROOT / "SLM" / "tools"))
    from auton_format import VERSION

    src = subprocess.run(["git", "-C", str(ROOT), "show",
                          "kernel-base-v3:kernels/x86_64/kernel/slm/neural/neural_backend.c"],
                         capture_output=True, text=True).stdout
    m = re.search(r"#define VERSION\s+(\d+)u", src)
    assert m and int(m.group(1)) == VERSION


def test_the_script_defaults_to_v3():
    assert 'REV="kernel-base-v3"' in SCRIPT.read_text()
