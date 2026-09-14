"""Compute a closed subsystem slice from a capability manifest.

The intent-to-OS design rests on shipping only what an image needs. That is not
checkable unless each spec declares what it *provides* and what it *depends on*,
which the front-matter added by plan intent-A now does.

A slice is **closed** when every subsystem it names has its dependencies in the
set too. The interesting output is not the slice — it is the refusal: when a
required capability transitively depends on an excluded one, the intent is
self-contradictory, and saying so before anything is generated is worth more
than a kernel that quietly contains what the manifest said to leave out.

    python agent/tools/capability_slice.py --requires framebuffer,input,terminal --excludes net
    python agent/tools/capability_slice.py --requires tcp --excludes mm      # refuses
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC_ROOT = ROOT / "agent" / "kernel_spec"


class SliceError(Exception):
    """A slice that cannot be built. Always carries why, never an empty result —
    an unknown capability silently yielding {} is the failure mode this whole
    module exists to prevent."""


@dataclass(frozen=True)
class Spec:
    name: str
    provides: tuple[str, ...]
    depends_on: tuple[str, ...]
    optional: tuple[str, ...]
    path: Path


def _parse_front_matter(text: str, path: Path) -> dict:
    """Read the leading `---` block. Deliberately not a YAML dependency: the
    block is three list fields and a comment, and kernel specs are read as plain
    text by the agents (base_agent.py), so the format must stay trivial."""
    if not text.startswith("---\n"):
        raise SliceError(f"{path}: no capability front-matter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise SliceError(f"{path}: unterminated front-matter block")
    out: dict = {}
    for line in text[4:end].splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith("["):
            items = [v.strip() for v in value[1:-1].split(",") if v.strip()]
            out[key.strip()] = items
        else:
            out[key.strip()] = value
    return out


def build_owner_index(specs: dict[str, Spec]) -> dict[str, str]:
    """capability -> owning subsystem, refusing a capability claimed by two.

    Two owners makes a slice ambiguous: requiring `pci` would pull in whichever
    spec happened to be read second. Caught at load, not at use.
    """
    owners: dict[str, str] = {}
    for name in sorted(specs):
        for cap in specs[name].provides:
            if cap in owners:
                raise SliceError(
                    f"capability {cap!r} provided by both {owners[cap]!r} "
                    f"and {name!r}; a capability has one owner"
                )
            owners[cap] = name
    return owners


def load_specs(spec_root: Path = SPEC_ROOT) -> dict[str, Spec]:
    specs: dict[str, Spec] = {}
    for sub in ("subsystems", "arch"):
        for path in sorted((spec_root / sub).glob("*.md")):
            fm = _parse_front_matter(path.read_text(encoding="utf-8"), path)
            name = fm.get("subsystem") or fm.get("arch")
            if not name:
                raise SliceError(f"{path}: front-matter names no subsystem or arch")
            spec = Spec(
                name=name,
                provides=tuple(fm.get("provides", [])),
                depends_on=tuple(fm.get("depends_on", [])),
                optional=tuple(fm.get("optional", [])),
                path=path,
            )
            if not spec.provides:
                raise SliceError(f"{path}: declares no capabilities")
            specs[name] = spec
    build_owner_index(specs)   # raises on a double-owned capability
    return specs


def capability_owner(specs: dict[str, Spec]) -> dict[str, str]:
    return build_owner_index(specs)


def _resolve(token: str, specs: dict[str, Spec], owners: dict[str, str]) -> str:
    """A manifest entry names either a subsystem or one of its capabilities."""
    if token in specs:
        return token
    if token in owners:
        return owners[token]
    raise SliceError(
        f"unknown capability or subsystem {token!r}. "
        f"Known subsystems: {', '.join(sorted(specs))}"
    )


@dataclass(frozen=True)
class Slice:
    subsystems: tuple[str, ...]
    capabilities: tuple[str, ...]
    requires: tuple[str, ...]
    excludes: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps({
            "subsystems": list(self.subsystems),
            "capabilities": list(self.capabilities),
            "requires": list(self.requires),
            "excludes": list(self.excludes),
        }, indent=2)


def capability_slice(
    requires: list[str],
    excludes: list[str] | None = None,
    specs: dict[str, Spec] | None = None,
) -> Slice:
    """The transitive subsystem set for `requires`, or a refusal naming the path.

    `excludes` may name a subsystem (`net`) or a single capability (`writable`).
    Excluding a capability excludes its owning subsystem only when that
    subsystem is reached *because of* it — excluding `writable` does not
    exclude `initramfs`, which the same spec provides.
    """
    specs = specs if specs is not None else load_specs()
    owners = capability_owner(specs)
    excludes = list(excludes or [])

    excluded_subsystems = {t for t in excludes if t in specs}
    excluded_caps = {t for t in excludes if t in owners and t not in specs}
    for token in excludes:
        if token not in specs and token not in owners:
            raise SliceError(
                f"unknown excluded capability or subsystem {token!r}. "
                f"An exclude that names nothing silently excludes nothing."
            )

    # A required capability that is itself excluded is the simplest contradiction.
    for token in requires:
        if token in excluded_subsystems or token in excluded_caps:
            raise SliceError(f"{token!r} is both required and excluded")

    roots = [(_resolve(t, specs, owners), t) for t in requires]

    resolved: set[str] = set()
    # Walk depth-first so a conflict can be reported with the path that caused it.
    def visit(name: str, path: tuple[str, ...], origin: str) -> None:
        if name in excluded_subsystems:
            raise SliceError(
                f"{origin!r} requires {name!r}, which is excluded.\n"
                f"  path: {' -> '.join(path + (name,))}\n"
                f"  The intent is self-contradictory; drop the exclude or the requirement."
            )
        if name in path:
            raise SliceError(
                f"dependency cycle: {' -> '.join(path + (name,))}"
            )
        if name in resolved:
            return
        spec = specs.get(name)
        if spec is None:
            raise SliceError(f"{name!r} is depended on but has no spec")
        for dep in spec.depends_on:
            visit(_resolve(dep, specs, owners), path + (name,), origin)
        resolved.add(name)

    for name, origin in roots:
        visit(name, (), origin)

    # Capabilities the slice carries: everything non-optional from each included
    # subsystem, plus the optional ones explicitly required. An optional
    # capability nobody asked for is exactly what should not ship.
    wanted = set(requires)
    caps: set[str] = set()
    for name in resolved:
        spec = specs[name]
        for cap in spec.provides:
            if cap in excluded_caps:
                continue
            if cap in spec.optional and cap not in wanted:
                continue
            caps.add(cap)

    return Slice(
        subsystems=tuple(sorted(resolved)),
        capabilities=tuple(sorted(caps)),
        requires=tuple(requires),
        excludes=tuple(excludes),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--requires", required=True, help="comma-separated")
    ap.add_argument("--excludes", default="", help="comma-separated")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    split = lambda s: [t.strip() for t in s.split(",") if t.strip()]  # noqa: E731
    try:
        result = capability_slice(split(args.requires), split(args.excludes))
    except SliceError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(result.to_json())
        return 0
    print(f"subsystems ({len(result.subsystems)}): {', '.join(result.subsystems)}")
    print(f"capabilities ({len(result.capabilities)}): {', '.join(result.capabilities)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
