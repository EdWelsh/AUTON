"""Parse and validate an artifact record — what an application needs.

A target definition says what an image runs *on*; a manifest says what it is
*for*. An artifact record says what an existing application *reaches for*, and it
is the contract the Analyst agent writes into (application-to-environment A1).

Three rules carry the weight, each the same rule this project already enforces
elsewhere, pointed at applications:

**Every fact carries a `source`** — observed, declared, inferred or unknown —
the vocabulary `target_spec` uses for machines. `observed` is reserved for
`observe.py`, as `probed` is for `probe_ingest.py`; `declared` and `inferred`
must cite `file:line` and quote the line; `unknown` must say where it looked.

**Every capability is drawn from a closed, typed index**
(`agent/app_spec/capabilities.yaml`). A name the index does not hold is refused
with the list of what it does hold, the refusal `intent_manifest` gives an
unknown sentence. An agent cannot talk the system into a capability that does
not exist.

**Ports are never inferred.** A listening port is declared or observed; one
that is only declared is used, and recorded as an assumption.

    python agent/tools/artifact_spec.py --validate analysis/app.artifact.yaml
    python agent/tools/artifact_spec.py --known lib
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
APP_SPEC = ROOT / "agent" / "app_spec"
INDEX = APP_SPEC / "capabilities.yaml"
BRIDGE = APP_SPEC / "kernel_bridge.yaml"

FORMAT = 1
SOURCES = ("observed", "declared", "inferred", "unknown")
CITING_SOURCES = ("declared", "inferred")
REQUIRED = ("application", "subject", "runtime", "facts")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

EXIT_REFUSED = 1
EXIT_UNREADABLE = 2


class ArtifactError(Exception):
    """A record that cannot be read at all. Always says what is missing."""


# --------------------------------------------------------------------------- #
# The index
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Kind:
    name: str
    description: str
    names: tuple[str, ...] = ()
    pattern: re.Pattern | None = None
    example: str = ""
    sources: tuple[str, ...] = SOURCES
    enabled: bool = True
    reason: str = ""


@dataclass(frozen=True)
class Index:
    kinds: dict[str, Kind]

    def refusal(self, capability: str) -> str | None:
        """Why `capability` is not in the vocabulary, or None if it is."""
        kind_name, sep, name = capability.partition(":")
        if not sep or not kind_name or not name:
            return (f"{capability!r} is not a typed capability: write kind:name, "
                    f"kinds {', '.join(sorted(self.kinds))}")
        kind = self.kinds.get(kind_name)
        if kind is None:
            return (f"{capability!r}: kind {kind_name!r} is not in the index; "
                    f"kinds are {', '.join(sorted(self.kinds))}")
        if not kind.enabled:
            return f"{capability!r}: kind {kind_name!r} is disabled — {kind.reason}"
        if kind.pattern is not None:
            if not kind.pattern.match(name):
                return (f"{capability!r} does not match {kind_name} names "
                        f"({kind.pattern.pattern}); for example {kind.example}")
            return None
        if name not in kind.names:
            return (f"{capability!r} is not in the index. Known {kind_name} names: "
                    f"{', '.join(kind.names)}. Add it to "
                    f"agent/app_spec/capabilities.yaml (a reviewed edit) rather than "
                    f"guessing a nearby name")
        return None


def load_index(path: Path = INDEX) -> Index:
    data = yaml.safe_load(path.read_text())
    kinds = {}
    for name, raw in (data.get("kinds") or {}).items():
        odd = [n for n in raw.get("names") or () if not isinstance(n, str)]
        if odd:
            # `null`, `yes`, `on` parse as None/True in YAML; quote them.
            raise ArtifactError(f"{path.name}: kind {name!r} has non-string names "
                                f"{odd!r}; quote them")
        pattern = raw.get("pattern")
        kinds[name] = Kind(
            name=name,
            description=raw.get("description", ""),
            names=tuple(raw.get("names") or ()),
            pattern=re.compile(pattern) if pattern else None,
            example=raw.get("example", ""),
            sources=tuple(raw.get("sources") or SOURCES),
            enabled=raw.get("enabled", True),
            reason=" ".join(str(raw.get("reason", "")).split()),
        )
    return Index(kinds=kinds)


def known(kind_name: str, index: Index | None = None) -> list[str]:
    """What a kind accepts: its names, or its pattern and an example."""
    index = index or load_index()
    kind = index.kinds.get(kind_name)
    if kind is None:
        raise ArtifactError(f"no kind {kind_name!r}; kinds are {', '.join(sorted(index.kinds))}")
    if not kind.enabled:
        return [f"(disabled) {kind.reason}"]
    if kind.pattern is not None:
        return [f"pattern {kind.pattern.pattern}", kind.example]
    return list(kind.names)


def load_bridge(path: Path = BRIDGE) -> list[dict]:
    return list(yaml.safe_load(path.read_text()).get("bridge") or [])


def kernel_capabilities(capability: str, bridge: list[dict] | None = None) -> list[str] | None:
    """The kernel capabilities an application capability needs on the AUTON
    substrate, or None when it has no kernel equivalent (which that substrate
    refuses rather than approximates)."""
    for entry in bridge if bridge is not None else load_bridge():
        if fnmatch.fnmatchcase(capability, entry["match"]):
            return list(entry["kernel"])
    return None


# --------------------------------------------------------------------------- #
# The record
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Evidence:
    file: str
    line: int
    quote: str


@dataclass(frozen=True)
class Fact:
    capability: str
    source: str
    evidence: tuple[Evidence, ...] = ()
    looked_at: tuple[str, ...] = ()
    observation: str | None = None


@dataclass(frozen=True)
class Artifact:
    path: Path
    application: str
    subject: dict
    runtime: dict
    facts: tuple[dict, ...]


@dataclass
class Report:
    """What validation found. `problems` empty is the only pass; each problem
    names the fact, what is wrong and what would fix it."""
    artifact: Artifact
    problems: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def load(path: str | Path) -> Artifact:
    """Read a record. Refuses only what makes it unreadable; per-fact defects
    are `problems`, so an Analyst sees every one at once."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        raise ArtifactError(f"{path}: no such file") from None
    except yaml.YAMLError as exc:
        raise ArtifactError(f"{path.name}: not valid YAML: {exc}") from None
    if not isinstance(data, dict):
        raise ArtifactError(f"{path.name}: expected a mapping at the top level")
    if data.get("format", FORMAT) != FORMAT:
        raise ArtifactError(f"{path.name}: format {data.get('format')!r}; this validator "
                            f"reads format {FORMAT}")
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise ArtifactError(f"{path.name}: missing {', '.join(missing)} "
                            f"(required: {', '.join(REQUIRED)})")
    if not isinstance(data["facts"], list):
        raise ArtifactError(f"{path.name}: facts must be a list")
    return Artifact(path=path, application=str(data["application"]),
                    subject=dict(data["subject"] or {}), runtime=dict(data["runtime"] or {}),
                    facts=tuple(f if isinstance(f, dict) else {"capability": repr(f)}
                                for f in data["facts"]))


def _evidence_problems(label: str, raw: list) -> list[str]:
    if not raw:
        return [f"{label}: a {CITING_SOURCES[0]} or {CITING_SOURCES[1]} fact needs evidence "
                f"— file, line and quote of the line that shows it"]
    problems = []
    for n, ev in enumerate(raw, 1):
        ev = ev if isinstance(ev, dict) else {}
        absent = [k for k in ("file", "line", "quote") if not ev.get(k)]
        if absent:
            problems.append(f"{label}: evidence {n} lacks {', '.join(absent)} "
                            f"(each item needs file, line and quote)")
        elif not isinstance(ev["line"], int) or ev["line"] < 1:
            problems.append(f"{label}: evidence {n} line {ev['line']!r} is not a line "
                            f"number (a positive integer)")
    return problems


def fact_problems(raw: dict, index: Index, *, runtime: bool = False) -> list[str]:
    """Every defect in one fact."""
    cap = str(raw.get("capability", ""))
    label = cap or "a fact with no capability"
    if not cap:
        return [f"{label}: give capability as kind:name"]
    if runtime and not cap.startswith("runtime:"):
        return [f"runtime is {cap!r}; it must be a runtime:… capability "
                f"({', '.join(known('runtime', index))})"]

    problems = []
    if (why := index.refusal(cap)) is not None:
        problems.append(why)

    source = raw.get("source")
    if source is None:
        return problems + [f"{label}: no source; give one of {', '.join(SOURCES)}"]
    if source not in SOURCES:
        return problems + [f"{label}: source {source!r} is not one of {', '.join(SOURCES)}"]

    kind = index.kinds.get(cap.partition(":")[0])
    if kind is not None and source not in kind.sources:
        problems.append(f"{label}: source {source!r} is not accepted for {kind.name} "
                        f"capabilities; use one of {', '.join(kind.sources)}")

    if source in CITING_SOURCES:
        problems += _evidence_problems(label, raw.get("evidence") or [])
    elif source == "unknown" and not raw.get("looked_at"):
        problems.append(f"{label}: an unknown fact must say where it looked (looked_at: "
                        f"[files]) — unknown is not a softer kind of absent")
    elif source == "observed" and not raw.get("observation"):
        problems.append(f"{label}: observed facts are written by observe.py, which always "
                        f"records the observation they came from; this one names none")
    return problems


def _cite(raw: dict) -> str:
    ev = (raw.get("evidence") or [{}])[0]
    return f"{ev.get('file', '?')}:{ev.get('line', '?')}"


def derive_assumptions(artifact: Artifact) -> list[str]:
    """What the record uses without having established it: ports only declared,
    and every unknown. The pattern intent_manifest uses for its defaults."""
    observed = {f.get("capability") for f in artifact.facts if f.get("source") == "observed"}
    out = []
    for raw in artifact.facts:
        cap, source = raw.get("capability", ""), raw.get("source")
        if cap in observed:
            continue
        if source == "declared" and cap.startswith("listen:"):
            out.append(f"{cap}: declared only ({_cite(raw)}), never observed")
        elif source == "unknown":
            out.append(f"{cap}: unknown (looked at {', '.join(raw.get('looked_at') or [])})")
    return out


def validate(path: str | Path, index: Index | None = None) -> Report:
    index = index or load_index()
    artifact = load(path)
    report = Report(artifact=artifact)

    tree_hash = str(artifact.subject.get("tree_hash", ""))
    if not SHA256.match(tree_hash):
        report.problems.append(
            "subject.tree_hash is missing or not a sha256: it ties the record to the "
            "exact tree analysed (GitWorkspace.stage_subject returns it)")

    report.problems += fact_problems(artifact.runtime, index, runtime=True)
    for raw in artifact.facts:
        report.problems += fact_problems(raw, index)
    report.assumptions = derive_assumptions(artifact)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--validate", metavar="FILE")
    ap.add_argument("--known", metavar="KIND")
    args = ap.parse_args(argv)

    if args.known:
        try:
            print("\n".join(known(args.known)))
        except ArtifactError as exc:
            print(f"INVALID: {exc}", file=sys.stderr)
            return EXIT_UNREADABLE
        return 0
    if not args.validate:
        ap.error("give --validate FILE or --known KIND")

    try:
        report = validate(args.validate)
    except ArtifactError as exc:
        print(f"UNREADABLE: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE
    for problem in report.problems:
        print(f"REFUSED: {problem}", file=sys.stderr)
    for assumption in report.assumptions:
        print(f"   assumed: {assumption}")
    if not report.ok:
        return EXIT_REFUSED
    print(f"OK {Path(args.validate).name}: {report.artifact.application}, "
          f"{len(report.artifact.facts)} fact(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
