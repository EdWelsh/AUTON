"""Resolve a capability manifest into the source list a build should compile.

The build compiles every `.c` under `kernel/`, so a manifest that excludes `net`
changes nothing about what is linked. This is the missing hop: manifest ->
capability slice -> source files.

    python agent/tools/build_manifest.py --service dhcp --tree kernels/x86_64
    python agent/tools/build_manifest.py --all --tree kernels/x86_64   # the full glob
    make -C kernels/x86_64 CSRC="$(build_manifest.py --service dhcp --tree ... --csrc)"

`--all` exists to prove the resolver against the status quo: it must reproduce
the glob byte-identically, because a refactor that changes the general image
while claiming to add scoping is two changes wearing one commit.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCE_MAP = ROOT / "agent" / "kernel_spec" / "source_map.yaml"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from capability_slice import SliceError, capability_slice  # noqa: E402

SOURCE_SUFFIXES = (".c", ".S")


class ManifestError(Exception):
    """Names the capability or the path. A build list that is silently short is
    a link error much later, in a file nobody was editing."""


@dataclass(frozen=True)
class SourceMap:
    mandatory_core: tuple[str, ...]
    core_provides: frozenset[str]
    capabilities: dict[str, tuple[str, ...]]

    @staticmethod
    def load(path: Path = SOURCE_MAP) -> "SourceMap":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return SourceMap(
            mandatory_core=tuple(data.get("mandatory_core") or ()),
            core_provides=frozenset(data.get("core_provides") or ()),
            capabilities={k: tuple(v) for k, v in (data.get("capabilities") or {}).items()},
        )


def _tree_sources(tree: Path) -> list[Path]:
    """Every source in the tree, in the order `find` yields sorted — the list
    the glob produces, and the thing --all must reproduce."""
    out = [p for p in tree.rglob("*") if p.suffix in SOURCE_SUFFIXES and p.is_file()]
    return sorted(out)


def _match(patterns: tuple[str, ...], rel: str) -> bool:
    for pat in patterns:
        # `kernel/arch/**` should match `kernel/arch/x86_64/boot.S`; fnmatch's
        # `*` already crosses separators, so `**` is normalised to `*`.
        if fnmatch.fnmatch(rel, pat.replace("**", "*")):
            return True
    return False


def resolve(
    requires: list[str],
    excludes: list[str],
    tree: Path,
    source_map: SourceMap | None = None,
) -> tuple[list[Path], list[Path], dict]:
    """Return (included, excluded, report) for a tree.

    `excluded` is returned rather than discarded: it is what the leakage test
    asserts against, and a caller that only sees the included list cannot check
    anything about what was left out.
    """
    source_map = source_map or SourceMap.load()
    try:
        sl = capability_slice(requires, excludes)
    except SliceError as exc:
        raise ManifestError(str(exc)) from exc

    all_sources = _tree_sources(tree)
    if not all_sources:
        raise ManifestError(f"{tree}: no .c or .S sources found")

    wanted_patterns: list[str] = list(source_map.mandatory_core)
    unmapped: list[str] = []
    for cap in sl.capabilities:
        if cap in source_map.core_provides:
            continue                    # already covered by mandatory_core
        pats = source_map.capabilities.get(cap)
        if pats is None:
            unmapped.append(cap)
            continue
        wanted_patterns.extend(pats)

    # De-duplicated by path: the mandatory core and a capability can match the
    # same file, and a source listed twice is a "multiple definition" link
    # error in a file nobody edited. `all_sources` is already unique, so the
    # guard is on callers appending extras that the core also matches.
    included, excluded, seen = [], [], set()
    for p in all_sources:
        rel = str(p.relative_to(tree))
        if rel in seen:
            continue
        seen.add(rel)
        (included if _match(tuple(wanted_patterns), rel) else excluded).append(p)

    report = {
        "subsystems": list(sl.subsystems),
        "capabilities": list(sl.capabilities),
        # A capability with no source mapping is reported, never silently
        # dropped: it means the image is missing something the manifest asked
        # for, and the symptom would be a link error in an unrelated file.
        "unmapped_capabilities": sorted(unmapped),
        "included": len(included),
        "excluded": len(excluded),
        "total": len(all_sources),
    }
    return included, excluded, report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tree", required=True)
    ap.add_argument("--service", help="a spec in kernel_spec/services/")
    ap.add_argument("--requires", default="", help="comma-separated capabilities")
    ap.add_argument("--excludes", default="")
    ap.add_argument("--all", action="store_true",
                    help="every source in the tree; proves the resolver against the glob")
    ap.add_argument("--csrc", action="store_true", help="print a space-separated list for make")
    ap.add_argument("--show-excluded", action="store_true")
    args = ap.parse_args(argv)

    tree = Path(args.tree)
    if not tree.is_absolute():
        tree = ROOT / tree

    try:
        if args.all:
            included, excluded, report = _tree_sources(tree), [], {"note": "full tree"}
        elif args.service:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from service_spec import load as load_service
            spec = load_service(ROOT / "agent" / "kernel_spec" / "services" / f"{args.service}.md")
            included, excluded, report = resolve(
                list(spec.requires), list(spec.excludes), tree)
        else:
            split = lambda s: [t.strip() for t in s.split(",") if t.strip()]  # noqa: E731
            if not args.requires:
                ap.error("give --service, --requires, or --all")
            included, excluded, report = resolve(
                split(args.requires), split(args.excludes), tree)
    except ManifestError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    if args.csrc:
        print(" ".join(str(p.relative_to(tree)) for p in included))
        return 0

    for key, value in report.items():
        print(f"{key}: {value}")
    if report.get("unmapped_capabilities"):
        print("WARNING: capabilities with no source mapping — the image will be "
              "missing them, and the symptom is a link error elsewhere.",
              file=sys.stderr)
    print()
    for p in included:
        print(f"  + {p.relative_to(tree)}")
    if args.show_excluded:
        for p in excluded:
            print(f"  - {p.relative_to(tree)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
