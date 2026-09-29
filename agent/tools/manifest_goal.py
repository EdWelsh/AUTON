"""Turn a manifest into work for the swarm (application-to-environment A7).

    python agent/tools/manifest_goal.py --manifest m.json --tree <workspace>

A manifest says what an image needs; a tree says what exists. What the tree
already implements is *satisfied*. What it does not becomes a **seed task** for
the existing Architect/Developer loop, and each seed carries the frozen gate
that decides it, from `agent/kernel_spec/capability_gates.yaml`. Nothing new is
gated here and no gate is invented: a missing capability with no gate is
refused, because a generation run nobody checks is worth nothing.

"What the tree lacks" is `build_manifest.resolve()`'s answer, not a second one:
capabilities with no source mapping, or a mapping with nothing behind it, and —
as `build_service.gate_capabilities` does — only those the manifest names
directly. A capability pulled in transitively is not the manifest's to answer for.

On a container substrate the host supplies the kernel, so there is nothing to
generate and the handoff is a no-op; the Packager (A8) takes it from there.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GATES = ROOT / "agent" / "kernel_spec" / "capability_gates.yaml"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_manifest import ManifestError, resolve  # noqa: E402
from intent_manifest import IntentError, Manifest  # noqa: E402

CONTAINER_SUBSTRATES = ("docker", "kubernetes", "server")


@dataclass
class Handoff:
    goal: str
    seed_tasks: list[dict] = field(default_factory=list)
    satisfied: list[str] = field(default_factory=list)


def load_gates(path: Path = GATES) -> dict[str, dict]:
    return dict(yaml.safe_load(path.read_text()).get("capabilities") or {})


def manifest_from_json(text: str) -> Manifest:
    d = json.loads(text)
    return Manifest(intent=d["intent"], matched=d["matched_rule"], requires=d["requires"],
                    excludes=d["excludes"], assets=d.get("assets", []),
                    markers=d.get("markers", []), assumptions=d.get("assumptions", []),
                    target=d.get("target", ""), decisions=d.get("decisions", []),
                    application=d.get("application", {}))


def _seed(cap: str, entry: dict) -> dict:
    gates = [f"KERNEL_TREE=<workspace> {g} exits 0" for g in entry["gates"]]
    return {
        "task_id": f"gen-{cap}",
        "title": f"Implement {cap}",
        "subsystem": Path(entry["spec"]).stem,
        "assigned_to": "developer",
        "dependencies": [],
        "priority": 1,
        "spec_reference": f"agent/kernel_spec/{entry['spec']}",
        "produces": list(entry["produces"]),
        "acceptance_criteria": gates,
        "description": (f"The manifest requires `{cap}` and this tree does not implement "
                        f"it. Implement it to {entry['spec']}; it is decided by "
                        f"{', '.join(entry['gates'])}, which you cannot see or edit."),
        "seed": True,
    }


def plan(manifest: Manifest, tree: Path, gates: dict[str, dict] | None = None) -> Handoff:
    substrate = (manifest.application or {}).get("substrate")
    if substrate in CONTAINER_SUBSTRATES:
        return Handoff(goal=(f"{manifest.intent}: the {substrate} substrate supplies the "
                             f"kernel; nothing to generate. Package it (A8)."))

    gates = gates if gates is not None else load_gates()
    try:
        _, _, report = resolve(list(manifest.requires), list(manifest.excludes), Path(tree))
    except ManifestError as exc:
        raise IntentError(f"{manifest.intent} does not resolve against {tree}: {exc}") from exc

    lacking = set(report["unmapped_capabilities"]) | set(report["phantom_capabilities"])
    missing = [c for c in manifest.requires if c in lacking]
    ungated = [c for c in missing if c not in gates]
    if ungated:
        raise IntentError(
            f"{manifest.intent} needs {', '.join(ungated)}, which this tree does not "
            f"implement, and no gate exists for it in capability_gates.yaml. A "
            f"generation task without a gate cannot be decided (completion PRD: every "
            f"run is decided by a pre-registered gate); add the gate first")

    seeds = [_seed(c, gates[c]) for c in missing]
    satisfied = [c for c in manifest.requires if c not in lacking]
    lines = [f"Build the kernel {manifest.intent} needs."]
    if satisfied:
        lines.append(f"Already implemented in this tree: {', '.join(satisfied)}.")
    for s in seeds:
        lines.append(f"Required, not yet implemented: {s['task_id'][4:]} — decided by "
                     f"{', '.join(g for g in gates[s['task_id'][4:]]['gates'])}.")
    return Handoff(goal="\n".join(lines), seed_tasks=seeds, satisfied=satisfied)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True, help="manifest JSON")
    ap.add_argument("--tree", required=True, help="the kernel workspace")
    ap.add_argument("--out", help="write {goal, seed_tasks} JSON here")
    args = ap.parse_args(argv)
    try:
        h = plan(manifest_from_json(Path(args.manifest).read_text()), Path(args.tree))
    except IntentError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    text = json.dumps({"goal": h.goal, "seed_tasks": h.seed_tasks,
                       "satisfied": h.satisfied}, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
