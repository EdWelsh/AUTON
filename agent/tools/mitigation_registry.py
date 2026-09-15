"""Load mitigations and join them to H4's errata verdicts.

H4 answers whether an erratum applies. This answers what can be done about it,
what that costs, and whether the image can even apply it.

The join produces four categories and keeps them apart:

    applicable     the erratum applies and nothing here addresses it
    mitigable      a mitigation exists and this image has what it needs
    declined       a mitigation exists and the image lacks its capabilities
    unmitigatable  the mitigation's own status says nothing can be done

`unmitigatable` is a real answer, not a gap. FDIV is in the registry precisely
because no software fix exists, and a registry that only recorded fixable
defects could not say the most important thing it can say.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MITIGATIONS = ROOT / "agent" / "kernel_spec" / "mitigations"
sys.path.insert(0, str(Path(__file__).resolve().parent))

REQUIRED = ("mitigation", "addresses", "class", "requires", "cost", "verify", "status")
CLASSES = {"fault", "semantic"}
STATUSES = {"implementable", "needs-microcode", "unmitigatable"}


class RegistryError(Exception):
    """Names the file and the field. A registry of mitigations is exactly the
    place where a vague error costs the most time."""


@dataclass(frozen=True)
class Mitigation:
    name: str
    addresses: tuple[str, ...]
    klass: str
    requires: tuple[str, ...]
    cost: str
    verify: str
    status: str
    path: Path

    @property
    def unmitigatable(self) -> bool:
        return self.status == "unmitigatable"


def _front_matter(text: str, path: Path) -> dict:
    if not text.startswith("---\n"):
        raise RegistryError(f"{path.name}: no front-matter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise RegistryError(f"{path.name}: unterminated front-matter")
    out: dict = {}
    key = None
    for raw in text[4:end].splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        if raw.startswith((" ", "\t")) and key:
            out[key] = f"{out[key]} {raw.strip()}".strip()
            continue
        k, sep, v = raw.partition(":")
        if not sep:
            raise RegistryError(f"{path.name}: cannot parse {raw!r}")
        key, v = k.strip(), v.strip()
        out[key] = ([x.strip() for x in v[1:-1].split(",") if x.strip()]
                    if v.startswith("[") else v)
    return out


def load_one(path: Path) -> Mitigation:
    data = _front_matter(path.read_text(encoding="utf-8"), path)
    missing = [f for f in REQUIRED if f not in data or data[f] == ""]
    if missing:
        raise RegistryError(f"{path.name}: missing field(s): {', '.join(missing)}")
    if data["mitigation"] != path.stem:
        raise RegistryError(
            f"{path.name}: 'mitigation' is {data['mitigation']!r} but the file is "
            f"{path.stem!r}; they address the same thing")
    if data["class"] not in CLASSES:
        raise RegistryError(
            f"{path.name}: class {data['class']!r} must be one of "
            f"{', '.join(sorted(CLASSES))} — a fault can be provoked, a wrong "
            f"answer must be compared against a reference, and they verify differently")
    if data["status"] not in STATUSES:
        raise RegistryError(f"{path.name}: status {data['status']!r} not in "
                            f"{', '.join(sorted(STATUSES))}")
    if not data["addresses"]:
        raise RegistryError(
            f"{path.name}: addresses no erratum. A mitigation that names none is "
            f"a change without a reason")
    return Mitigation(
        name=data["mitigation"], addresses=tuple(data["addresses"]),
        klass=data["class"], requires=tuple(data["requires"]),
        cost=data["cost"], verify=data["verify"], status=data["status"], path=path,
    )


def load_all(d: Path = MITIGATIONS) -> dict[str, Mitigation]:
    out: dict[str, Mitigation] = {}
    for p in sorted(d.glob("*.md")):
        if p.name == "README.md":
            continue
        m = load_one(p)
        out[m.name] = m
    return out


@dataclass
class Assessment:
    applicable: list = field(default_factory=list)
    mitigable: list = field(default_factory=list)
    declined: list = field(default_factory=list)
    unmitigatable: list = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {k: len(getattr(self, k)) for k in
                ("applicable", "mitigable", "declined", "unmitigatable")}


def assess(applicable_errata: list[str], image_capabilities: set[str],
           registry: dict[str, Mitigation] | None = None) -> Assessment:
    """Sort applicable errata into what can be done about each.

    `image_capabilities` is the slice the image actually contains. A mitigation
    needing `vmm` in an image without it is **declined**, not mitigated — and
    saying so is the point, because the alternative is claiming a fix that was
    never applied.
    """
    registry = registry if registry is not None else load_all()
    by_erratum: dict[str, list[Mitigation]] = {}
    for m in registry.values():
        for e in m.addresses:
            by_erratum.setdefault(e, []).append(m)

    out = Assessment()
    for erratum in applicable_errata:
        candidates = by_erratum.get(erratum, [])
        if not candidates:
            # Never silently dropped: the registry's job includes saying what
            # it cannot fix.
            out.applicable.append((erratum, None, "no mitigation in the registry"))
            continue
        for m in candidates:
            if m.unmitigatable:
                out.unmitigatable.append((erratum, m, m.cost))
            elif set(m.requires) <= image_capabilities:
                out.mitigable.append((erratum, m, m.cost))
            else:
                lacking = sorted(set(m.requires) - image_capabilities)
                out.declined.append(
                    (erratum, m, f"image lacks {', '.join(lacking)}"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--errata", default="", help="comma-separated applicable errata")
    ap.add_argument("--capabilities", default="", help="comma-separated image capabilities")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)

    try:
        registry = load_all()
    except RegistryError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1

    if args.list or not args.errata:
        print(f"{len(registry)} mitigation(s)")
        for m in registry.values():
            print(f"  {m.name:24s} {m.klass:9s} {m.status:16s} "
                  f"addresses {', '.join(m.addresses)}")
            print(f"  {'':24s} requires {', '.join(m.requires) or 'nothing'}")
            print(f"  {'':24s} cost: {m.cost}")
        return 0

    split = lambda s: [t.strip() for t in s.split(",") if t.strip()]  # noqa: E731
    a = assess(split(args.errata), set(split(args.capabilities)), registry)
    for k, v in a.counts().items():
        print(f"{k}: {v}")
    for label in ("mitigable", "declined", "unmitigatable", "applicable"):
        for erratum, m, why in getattr(a, label):
            print(f"  [{label}] {erratum}"
                  + (f" -> {m.name}" if m else "") + f" ({why})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
