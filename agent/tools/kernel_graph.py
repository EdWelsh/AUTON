"""Extract a structural graph of a kernel tree from clang's AST.

Why this exists: AUTON's premise is that agents write the kernel
(`README.md:11`). The hand-written x86_64 tree is therefore a *reference*, not
a product — and what is worth keeping from a reference is its structure, not
its text. This tool captures that structure so the source can be retired while
remaining useful for two things the source itself serves badly:

  fine-tuning       (spec section -> the symbols that implement it) pairs are a
                    far denser training signal than raw C, and they survive a
                    rewrite in a different style or for a different target.
  vendor alignment  vendor documentation describes registers and protocols; the
                    graph shows which function touched which offset, so doc
                    text can be aligned to real binding code.

Usage:
    python agent/tools/kernel_graph.py --arch x86_64 --output .artifacts/kernel-graph
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Subsystem directory -> the spec file that governs it. This mapping is the
# link that makes the graph useful as training data: it turns "this function
# exists" into "this function implements that requirement".
SPEC_FOR_SUBSYSTEM = {
    "boot": "subsystems/boot.md",
    "mm": "subsystems/mm.md",
    "lib": "subsystems/mm.md",
    "sched": "subsystems/sched.md",
    "ipc": "subsystems/ipc.md",
    "dev": "subsystems/dev.md",
    "drivers": "subsystems/drivers.md",
    "net": "subsystems/net.md",
    "server": "subsystems/net.md",
    "slm": "subsystems/slm.md",
    "sys": "subsystems/sys.md",
    "arch": "arch/{arch}.md",
}


def subsystem_of(path: Path, kernel_root: Path) -> str:
    rel = path.relative_to(kernel_root)
    return rel.parts[0] if len(rel.parts) > 1 else "root"


def clang_ast(src: Path, include: Path) -> dict | None:
    """Parse one translation unit. Kernel C is freestanding, so say so."""
    # -ffreestanding WITHOUT -nostdinc: clang supplies its own freestanding
    # <stdint.h>, and hiding it makes every uint32_t degrade to int — which
    # would silently corrupt every signature in the training data.
    cmd = [
        "clang", "-Xclang", "-ast-dump=json", "-fsyntax-only",
        "-ffreestanding", f"-I{include}", str(src),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=120).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    try:
        return json.loads(out)
    except (json.JSONDecodeError, ValueError):
        return None


def walk(node: dict, current_file: str, out: dict, want: str,
         ids: dict[str, str] | None = None) -> str:
    """Walk the AST, tracking the current file.

    clang emits `loc.file` only when it CHANGES, so a naive reader attributes
    every symbol after the first to the wrong file. The file is sticky.
    """
    loc = node.get("loc") or {}
    if loc.get("file"):
        current_file = loc["file"]
    kind = node.get("kind")
    in_target = current_file.endswith(want)

    if in_target and kind == "FunctionDecl" and node.get("name"):
        calls: list[str] = []
        _collect_calls(node, calls, ids or {})
        out["functions"].append({
            "name": node["name"],
            "signature": (node.get("type") or {}).get("qualType", ""),
            "line": loc.get("line"),
            "static": node.get("storageClass") == "static",
            "defined": any(c.get("kind") == "CompoundStmt"
                           for c in node.get("inner", [])),
            "calls": sorted(set(calls)),
        })
    elif in_target and kind == "RecordDecl" and node.get("name"):
        out["structs"].append({
            "name": node["name"],
            "line": loc.get("line"),
            "fields": [
                {"name": f.get("name"),
                 "type": (f.get("type") or {}).get("qualType", "")}
                for f in node.get("inner", []) if f.get("kind") == "FieldDecl"
            ],
        })
    elif in_target and kind == "EnumDecl":
        out["enums"].append({
            "name": node.get("name") or "(anonymous)",
            "line": loc.get("line"),
            "values": [c.get("name") for c in node.get("inner", [])
                       if c.get("kind") == "EnumConstantDecl"],
        })

    for child in node.get("inner", []) or []:
        current_file = walk(child, current_file, out, want, ids)
    return current_file


def _index_decl_ids(node: dict, table: dict[str, str]) -> None:
    """Map AST node id -> function name, for the whole translation unit.

    clang emits `referencedDecl` in full the first time a function is
    referenced and then abbreviates it to `{"id": ...}`. Reading only the full
    form drops most call edges — measured at 188 edges across 158 functions
    before this, which is far too sparse for a kernel.
    """
    if node.get("kind") == "FunctionDecl" and node.get("name") and node.get("id"):
        table[node["id"]] = node["name"]
    for child in node.get("inner", []) or []:
        _index_decl_ids(child, table)


def _collect_calls(node: dict, acc: list[str], ids: dict[str, str]) -> None:
    """Callees referenced anywhere inside a function body."""
    if node.get("kind") == "DeclRefExpr":
        ref = node.get("referencedDecl") or {}
        name = ref.get("name")
        if name and ref.get("kind") == "FunctionDecl":
            acc.append(name)
        elif not name and ref.get("id") in ids:
            acc.append(ids[ref["id"]])     # abbreviated back-reference
    for child in node.get("inner", []) or []:
        _collect_calls(child, acc, ids)


INCLUDE_RE = re.compile(r'^\s*#\s*include\s+[<"]([^>"]+)[>"]', re.M)
DEFINE_RE = re.compile(r'^\s*#\s*define\s+([A-Za-z_]\w*)(?:\s+(.+?))?\s*$', re.M)


def build(arch: str) -> dict:
    kernel_root = ROOT / "kernels" / arch / "kernel"
    include = kernel_root / "include"
    sources = sorted(
        p for p in kernel_root.rglob("*")
        if p.suffix in (".c", ".h", ".S") and p.is_file()
    )

    graph: dict = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "arch": arch,
        "source_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=ROOT).stdout.strip(),
        "files": [], "symbols": [], "structs": [], "enums": [],
        "macros": [], "subsystems": {}, "unparsed": [],
    }

    for src in sources:
        rel = str(src.relative_to(ROOT))
        text = src.read_text(errors="replace")
        sub = subsystem_of(src, kernel_root)
        graph["files"].append({
            "path": rel,
            "subsystem": sub,
            "lines": len(text.splitlines()),
            "includes": sorted(set(INCLUDE_RE.findall(text))),
        })
        # Macros are preprocessor-only, so they never appear in the AST.
        for name, value in DEFINE_RE.findall(text):
            graph["macros"].append({
                "name": name, "file": rel, "subsystem": sub,
                "value": (value or "").strip()[:120],
            })

        if src.suffix != ".c":
            continue
        ast = clang_ast(src, include)
        if ast is None:
            graph["unparsed"].append(rel)
            continue
        found = {"functions": [], "structs": [], "enums": []}
        decl_ids: dict[str, str] = {}
        _index_decl_ids(ast, decl_ids)
        walk(ast, "", found, src.name, decl_ids)
        for fn in found["functions"]:
            graph["symbols"].append({**fn, "file": rel, "subsystem": sub,
                                     "kind": "function"})
        for st in found["structs"]:
            graph["structs"].append({**st, "file": rel, "subsystem": sub})
        for en in found["enums"]:
            graph["enums"].append({**en, "file": rel, "subsystem": sub})

    # Reverse edges: who calls me.
    by_name = {s["name"]: s for s in graph["symbols"]}
    callers = defaultdict(set)
    for s in graph["symbols"]:
        for callee in s["calls"]:
            if callee in by_name:
                callers[callee].add(s["name"])
    for s in graph["symbols"]:
        s["called_by"] = sorted(callers.get(s["name"], ()))

    # Subsystem rollup and cross-subsystem dependency edges.
    subs: dict[str, dict] = defaultdict(
        lambda: {"files": 0, "lines": 0, "symbols": 0, "depends_on": set()})
    for f in graph["files"]:
        subs[f["subsystem"]]["files"] += 1
        subs[f["subsystem"]]["lines"] += f["lines"]
    for s in graph["symbols"]:
        subs[s["subsystem"]]["symbols"] += 1
        for callee in s["calls"]:
            target = by_name.get(callee)
            if target and target["subsystem"] != s["subsystem"]:
                subs[s["subsystem"]]["depends_on"].add(target["subsystem"])
    graph["subsystems"] = {
        k: {**v, "depends_on": sorted(v["depends_on"]),
            "spec": SPEC_FOR_SUBSYSTEM.get(k, "").replace("{arch}", arch)}
        for k, v in sorted(subs.items())
    }
    return graph


def training_pairs(graph: dict) -> list[dict]:
    """(spec section -> what implements it) pairs, the fine-tuning payload.

    This is the artifact the source cannot provide: it states the requirement
    and the shape of a known-good implementation, without pinning the text. It
    stays valid when the same requirement is regenerated in another style, or
    for another architecture.
    """
    pairs = []
    for name, sub in graph["subsystems"].items():
        if not sub["spec"]:
            continue
        syms = [s for s in graph["symbols"] if s["subsystem"] == name]
        if not syms:
            continue
        pairs.append({
            "spec": sub["spec"],
            "subsystem": name,
            "depends_on": sub["depends_on"],
            "implemented_by": [
                {"name": s["name"], "signature": s["signature"],
                 "exported": not s["static"], "calls": s["calls"]}
                for s in sorted(syms, key=lambda x: x["name"])
            ],
            "structs": [s["name"] for s in graph["structs"]
                        if s["subsystem"] == name],
            "constants": sorted({m["name"] for m in graph["macros"]
                                 if m["subsystem"] == name}),
            "reference_lines": sub["lines"],
        })
    return pairs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Graph a kernel tree for reuse as training data")
    ap.add_argument("--arch", default="x86_64")
    ap.add_argument("--output", default=".artifacts/kernel-graph")
    args = ap.parse_args(argv)

    graph = build(args.arch)
    out = ROOT / args.output
    out.mkdir(parents=True, exist_ok=True)
    (out / "graph.json").write_text(json.dumps(graph, indent=2))

    pairs = training_pairs(graph)
    (out / "spec-to-implementation.jsonl").write_text(
        "\n".join(json.dumps(p) for p in pairs) + "\n")

    exported = [s for s in graph["symbols"] if not s["static"]]
    print(f"arch {graph['arch']} @ {graph['source_commit'][:8]}")
    print(f"  files      {len(graph['files'])}")
    print(f"  functions  {len(graph['symbols'])} ({len(exported)} exported)")
    print(f"  structs    {len(graph['structs'])}")
    print(f"  enums      {len(graph['enums'])}")
    print(f"  macros     {len(graph['macros'])}")
    if graph["unparsed"]:
        print(f"  UNPARSED   {len(graph['unparsed'])}: {graph['unparsed'][:4]}")
    print(f"  training pairs {len(pairs)} -> {args.output}/spec-to-implementation.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
