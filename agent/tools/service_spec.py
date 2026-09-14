"""Parse, validate and resolve a service spec.

A service spec composes capabilities the subsystem index provides and adds the
protocol behaviour specific to one image. This module turns it into a closed
subsystem slice, and refuses it when the spec is self-contradictory.

Everything here fails loudly and names the offending field. A service spec that
validates but means something other than what it says is the expensive failure:
it is discovered after a kernel has been generated from it.

    python agent/tools/service_spec.py --validate agent/kernel_spec/services/dhcp.md
    python agent/tools/service_spec.py --resolve  agent/kernel_spec/services/dhcp.md
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capability_slice import (  # noqa: E402
    Slice,
    SliceError,
    Spec,
    capability_owner,
    capability_slice,
    load_specs,
)

SERVICES_DIR = Path(__file__).resolve().parents[1] / "kernel_spec" / "services"

REQUIRED_FIELDS = ("service", "requires", "excludes", "entry", "markers", "assets")
LIST_FIELDS = ("requires", "excludes", "markers", "assets")


class ServiceSpecError(Exception):
    """Always names the field. 'invalid spec' sends an author reading the whole
    file to find which line was wrong."""


@dataclass(frozen=True)
class ServiceSpec:
    service: str
    requires: tuple[str, ...]
    excludes: tuple[str, ...]
    entry: str
    markers: tuple[str, ...]
    assets: tuple[str, ...]
    path: Path

    def resolve(self, specs: dict[str, Spec] | None = None) -> Slice:
        """The closed subsystem slice this service needs, or a refusal."""
        try:
            return capability_slice(list(self.requires), list(self.excludes), specs)
        except SliceError as exc:
            raise ServiceSpecError(f"{self.path.name}: {exc}") from exc


def _parse_front_matter(text: str, path: Path) -> dict:
    """Front-matter as a small subset of YAML: `key: value`, `key: [a, b]`, and
    a `key:` followed by `  - item` lines. Hand-rolled for the same reason the
    subsystem index is — these files are also read as plain text by agents, so
    the format must stay obvious."""
    if not text.startswith("---\n"):
        raise ServiceSpecError(f"{path.name}: no front-matter block")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ServiceSpecError(f"{path.name}: unterminated front-matter block")

    out: dict = {}
    pending: str | None = None
    for raw in text[4:end].splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        if raw.startswith(("  - ", "- ")):
            if pending is None:
                raise ServiceSpecError(
                    f"{path.name}: list item {raw.strip()!r} belongs to no field"
                )
            item = raw.split("-", 1)[1].strip()
            out.setdefault(pending, []).append(item.strip('"').strip("'"))
            continue
        key, sep, value = raw.partition(":")
        if not sep:
            raise ServiceSpecError(f"{path.name}: cannot parse front-matter line {raw!r}")
        key, value = key.strip(), value.strip()
        if value.startswith("["):
            out[key] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
            pending = None
        elif value:
            out[key] = value.strip('"').strip("'")
            pending = None
        else:
            out[key] = []
            pending = key
    return out


def load(path: str | Path, specs: dict[str, Spec] | None = None) -> ServiceSpec:
    """Parse and validate. Raises ServiceSpecError naming the field at fault."""
    path = Path(path)
    if not path.exists():
        raise ServiceSpecError(f"{path}: no such service spec")
    data = _parse_front_matter(path.read_text(encoding="utf-8"), path)

    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        raise ServiceSpecError(f"{path.name}: missing field(s): {', '.join(missing)}")

    for field in LIST_FIELDS:
        if not isinstance(data[field], list):
            raise ServiceSpecError(
                f"{path.name}: field {field!r} must be a list, got {data[field]!r}"
            )
    for field in ("service", "entry"):
        if not isinstance(data[field], str) or not data[field]:
            raise ServiceSpecError(f"{path.name}: field {field!r} must be a non-empty string")

    # The filename is how the factory addresses a service; a mismatch means one
    # of the two is a typo and the build would act on the wrong one.
    if data["service"] != path.stem:
        raise ServiceSpecError(
            f"{path.name}: field 'service' is {data['service']!r} but the file is "
            f"{path.stem!r}; they address the same thing and must agree"
        )
    if not data["requires"]:
        raise ServiceSpecError(f"{path.name}: field 'requires' is empty; a service needs something")
    if not data["markers"]:
        raise ServiceSpecError(
            f"{path.name}: field 'markers' is empty; without markers the image "
            f"cannot be verified and the spine has nothing to assert"
        )

    # Capability names must exist in the index, or `requires` is decoration.
    specs = specs if specs is not None else load_specs()
    known = set(specs) | set(capability_owner(specs))
    for field in ("requires", "excludes"):
        unknown = [c for c in data[field] if c not in known]
        if unknown:
            raise ServiceSpecError(
                f"{path.name}: field {field!r} names unknown capabilities: "
                f"{', '.join(unknown)}"
            )

    overlap = set(data["requires"]) & set(data["excludes"])
    if overlap:
        raise ServiceSpecError(
            f"{path.name}: {', '.join(sorted(overlap))} in both 'requires' and 'excludes'"
        )

    return ServiceSpec(
        service=data["service"],
        requires=tuple(data["requires"]),
        excludes=tuple(data["excludes"]),
        entry=data["entry"],
        markers=tuple(data["markers"]),
        assets=tuple(data["assets"]),
        path=path,
    )


def load_all(services_dir: Path = SERVICES_DIR) -> dict[str, ServiceSpec]:
    specs = load_specs()
    return {
        p.stem: load(p, specs)
        for p in sorted(services_dir.glob("*.md"))
        if p.name != "README.md"
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec", nargs="?", help="path to a service spec")
    ap.add_argument("--validate", metavar="SPEC")
    ap.add_argument("--resolve", metavar="SPEC")
    ap.add_argument("--all", action="store_true", help="validate every service spec")
    args = ap.parse_args(argv)

    try:
        if args.all:
            for name, spec in load_all().items():
                sl = spec.resolve()
                print(f"OK  {name:12s} entry={spec.entry:20s} "
                      f"{len(sl.subsystems)} subsystems, {len(spec.markers)} markers")
            return 0

        target = args.resolve or args.validate or args.spec
        if not target:
            ap.error("give a spec path, or --all")
        spec = load(target)
        if args.resolve:
            sl = spec.resolve()
            print(f"service:      {spec.service}")
            print(f"entry:        {spec.entry}")
            print(f"subsystems:   {', '.join(sl.subsystems)}")
            print(f"capabilities: {', '.join(sl.capabilities)}")
            if spec.assets:
                print(f"assets:       {', '.join(spec.assets)}")
            return 0
        spec.resolve()   # validation includes resolvability
        print(f"OK {spec.path.name}: {spec.service}, entry {spec.entry}, "
              f"{len(spec.markers)} markers")
        return 0
    except ServiceSpecError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
