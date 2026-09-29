"""The swarm handoff (A7): what a tree lacks becomes gated generation work.

A manifest names kernel capabilities. Those the tree already implements are
satisfied; those it does not become seed tasks for the existing loop, each
carrying the frozen gate that decides it. A missing capability with no gate is
refused, never handed over ungated.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from capability_slice import capability_owner, load_specs  # noqa: E402
from intent_manifest import IntentError, Manifest  # noqa: E402
from manifest_goal import GATES, load_gates, main, plan  # noqa: E402


def _tree(tmp_path, *files) -> Path:
    tree = tmp_path / "tree"
    for rel in ("kernel/arch/x86_64/boot.S", "kernel/boot/entry.c", "kernel/lib/kprintf.c",
                *files):
        p = tree / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("/* */\n")
    return tree


def _manifest(requires, **kw) -> Manifest:
    return Manifest(intent="application:x@abc", matched="artifact", requires=list(requires),
                    excludes=[], assets=[], markers=[], **kw)


def test_an_unimplemented_capability_becomes_a_gated_seed(tmp_path):
    tree = _tree(tmp_path, "kernel/lib/phys.c")
    h = plan(_manifest(["boot", "vmm"]), tree)
    [seed] = h.seed_tasks
    assert seed["task_id"] == "gen-vmm" and seed["assigned_to"] == "developer"
    assert seed["produces"] == ["kernel/mm/vmm.c"]
    assert any("run_vmm_test.sh" in c for c in seed["acceptance_criteria"])
    assert "subsystems/mm.md" in seed["spec_reference"]
    assert "boot" in h.satisfied


def test_a_mapping_with_nothing_behind_it_counts_as_missing(tmp_path):
    """tcp is mapped to kernel/net/tcp.c; a tree without that file does not
    provide it, and has no gate for it — refused, not silently satisfied."""
    tree = _tree(tmp_path)
    with pytest.raises(IntentError) as exc:
        plan(_manifest(["tcp"]), tree)
    assert "tcp" in str(exc.value) and "no gate" in str(exc.value)


def test_a_missing_capability_with_no_gate_is_refused(tmp_path):
    tree = _tree(tmp_path)
    with pytest.raises(IntentError, match="processes"):
        plan(_manifest(["processes"]), tree)


def test_a_fully_satisfied_manifest_needs_no_generation(tmp_path):
    tree = _tree(tmp_path, "kernel/net/tcp.c", "kernel/net/ipv4.c")
    h = plan(_manifest(["tcp", "sockets"]), tree)
    assert h.seed_tasks == []
    assert {"tcp", "sockets"} <= set(h.satisfied)


def test_a_container_manifest_is_a_no_op(tmp_path):
    m = _manifest([], application={"substrate": "docker", "name": "x"})
    h = plan(m, _tree(tmp_path))
    assert h.seed_tasks == [] and "docker" in h.goal


def test_the_goal_names_what_is_satisfied_and_what_is_to_build(tmp_path):
    tree = _tree(tmp_path, "kernel/lib/phys.c")
    h = plan(_manifest(["allocator", "vmm"]), tree)
    assert "vmm" in h.goal and "allocator" in h.goal and "run_vmm_test.sh" in h.goal


# --------------------------------------------------------------------------- #
# The gate table itself
# --------------------------------------------------------------------------- #

def test_every_gate_capability_is_real_and_every_gate_exists():
    specs = load_specs()
    real = set(specs) | set(capability_owner(specs))
    for cap, entry in load_gates().items():
        assert cap in real, f"{cap} is not a kernel capability"
        assert (ROOT / "agent" / "kernel_spec" / entry["spec"]).is_file(), entry["spec"]
        for gate in entry["gates"]:
            script = ROOT / gate
            assert script.is_file(), gate
            text = script.read_text()
            for rel in entry["produces"]:
                assert rel in text, f"{gate} never looks for {rel}"


def test_the_table_lives_where_the_docs_say():
    assert GATES == ROOT / "agent" / "kernel_spec" / "capability_gates.yaml"
    assert yaml.safe_load(GATES.read_text())["version"] == 1


def test_cli_writes_seeds(tmp_path, capsys):
    tree = _tree(tmp_path, "kernel/lib/phys.c")
    mf = tmp_path / "m.json"
    mf.write_text(_manifest(["vmm"]).to_json())
    assert main(["--manifest", str(mf), "--tree", str(tree)]) == 0
    out = capsys.readouterr().out
    assert "gen-vmm" in out
