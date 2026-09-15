"""Given a symbol dump and a set of excluded capabilities, prove absence.

Attribution is by object file, not by symbol name. A name-based list would be a
second source of truth that drifts from the source map, and it would miss
anything renamed or static. Every source a capability maps to is compiled, its
defined symbols recorded, and the image checked for those.

Naming is also why this compiles rather than greps: a symbol that was inlined
away is genuinely absent, and one that survived under another name is not.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from build_manifest import SourceMap, _match, _tree_sources  # noqa: E402

# Uppercase only: nm lowercases file-local symbols, and a static cannot leak
# across a link. Attributing them by name produced a false positive — `seg.0`
# is a static in netif.c that happens to share a name with one in tcp.c, and
# the check reported tcp as leaking into an image that does not contain it.
DEFINED = re.compile(r"^\s*[0-9a-fA-F]*\s*([TDBR])\s+(\S+)\s*$")


def defined_symbols(nm_output: str) -> set[str]:
    """Symbols the image defines. Undefined ones (`U`) are references, not
    content — an image that merely mentions a name has not shipped it."""
    out = set()
    for line in nm_output.splitlines():
        m = DEFINED.match(line)
        if m:
            out.add(m.group(2))
    return out


def sources_for(capabilities: list[str], source_map: SourceMap, tree: Path) -> list[Path]:
    pats: list[str] = []
    for cap in capabilities:
        pats.extend(source_map.capabilities.get(cap, ()))
    if not pats:
        return []
    return [p for p in _tree_sources(tree)
            if _match(tuple(pats), str(p.relative_to(tree)))]


def symbols_defined_by(source: Path, tree: Path) -> set[str]:
    """Compile one source and read what it defines. Requires the cross
    compiler; without it the check cannot be performed and says so rather than
    passing."""
    import os
    import tempfile

    cc = os.environ.get("CC") or "x86_64-elf-gcc"
    nm = os.environ.get("NM") or "x86_64-elf-nm"
    with tempfile.NamedTemporaryFile(suffix=".o", delete=False) as f:
        obj = f.name
    try:
        r = subprocess.run(
            [cc, "-c", str(source), "-o", obj,
             f"-I{tree}/kernel/include", "-ffreestanding", "-w"],
            capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return set()
        r = subprocess.run([nm, obj], capture_output=True, text=True, timeout=30)
        return defined_symbols(r.stdout)
    except (OSError, subprocess.SubprocessError):
        return set()
    finally:
        Path(obj).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", required=True)
    ap.add_argument("--tree", required=True)
    ap.add_argument("--excludes", required=True)
    ap.add_argument("--image", default="")
    ap.add_argument("--report", default="",
                    help="write the measurement as JSON. The PRD tracks leakage "
                         "as a number with a target of 0, and a pass/fail cannot "
                         "be tracked over time.")
    ap.add_argument("--stubs", default="",
                    help="a gen_absent.py stub list; those symbols are reported "
                         "as absence stubs rather than as leaks")
    args = ap.parse_args(argv)

    tree = Path(args.tree)
    excludes = [t.strip() for t in args.excludes.split(",") if t.strip()]
    source_map = SourceMap.load()

    # An exclude naming a subsystem means every capability that subsystem
    # provides. Resolved through the spec index so `--excludes net` means the
    # same thing here as it does in a manifest.
    from capability_slice import capability_owner, load_specs
    specs = load_specs()
    owners = capability_owner(specs)
    caps: list[str] = []
    for token in excludes:
        if token in specs:
            caps.extend(specs[token].provides)
        elif token in owners:
            caps.append(token)
        else:
            print(f"UNKNOWN: {token!r} is neither a subsystem nor a capability. "
                  f"An exclude that names nothing excludes nothing.", file=sys.stderr)
            return 2

    sources = sources_for(caps, source_map, tree)
    if not sources:
        print(f"no sources map to {args.excludes} in {tree} — nothing to check.",
              file=sys.stderr)
        return 2

    image_syms = defined_symbols(Path(args.symbols).read_text())
    if not image_syms:
        print(f"no defined symbols read from {args.image} — refusing to report "
              f"a clean result from an empty dump.", file=sys.stderr)
        return 2

    stubbed: set[str] = set()
    if args.stubs and Path(args.stubs).exists():
        stubbed = {ln.strip() for ln in Path(args.stubs).read_text().splitlines()
                   if ln.strip()}

    leaked: dict[str, set[str]] = {}
    stub_hits: set[str] = set()
    unreadable: list[Path] = []
    for src in sources:
        owned = symbols_defined_by(src, tree)
        if not owned:
            unreadable.append(src)
            continue
        hit = owned & image_syms
        # A generated absence stub carries the excluded capability's *name* but
        # none of its behaviour — that is the point of it. Reported separately,
        # never silently forgiven, because a stub list that drifts from what was
        # generated would forgive a real leak.
        stub_hits |= hit & stubbed
        hit -= stubbed
        if hit:
            leaked[str(src.relative_to(tree))] = hit

    print(f"image:    {args.image}")
    print(f"excludes: {args.excludes}  ({len(sources)} source files, "
          f"{len(image_syms)} symbols in the image)")
    if unreadable:
        # Not a pass. A source that could not be compiled contributed no known
        # symbols, so its absence was never actually checked.
        print(f"UNCHECKED: {len(unreadable)} source(s) could not be compiled for "
              f"attribution: {', '.join(str(p.name) for p in unreadable[:4])}")

    if stub_hits:
        print(f"  {len(stub_hits)} symbol(s) present as generated absence stubs: "
              f"{', '.join(sorted(stub_hits))}")

    if args.report:
        import json
        measurement = {
            "image": args.image,
            "excludes": excludes,
            "capabilities_checked": sorted(caps),
            "sources_attributed": len(sources) - len(unreadable),
            "sources_unattributable": len(unreadable),
            "image_symbols": len(image_syms),
            "leaked_symbols": sum(len(v) for v in leaked.values()),
            "leaked_by_source": {k: sorted(v) for k, v in leaked.items()},
            "absence_stubs": sorted(stub_hits),
            # Inconclusive is not clean. A run that could not attribute every
            # source has not checked them, and recording it as 0 would put a
            # false zero into a series the PRD tracks.
            "conclusive": not unreadable,
        }
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(measurement, indent=2) + "\n")
        print(f"  report -> {args.report}")

    if leaked:
        print(f"\nLEAKAGE: {sum(len(v) for v in leaked.values())} symbol(s) from "
              f"excluded capabilities are present in the image")
        for src, syms in sorted(leaked.items()):
            print(f"  {src}: {', '.join(sorted(syms)[:6])}"
                  + (" ..." if len(syms) > 6 else ""))
        return 1

    if unreadable:
        print("\nLEAKAGE: INCONCLUSIVE — some sources were not attributable")
        return 1
    print("\nLEAKAGE: none — excluded capabilities contribute no symbols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
