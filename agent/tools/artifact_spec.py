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

# The same hash the workspace takes when it stages a subject; one definition.
if str(ROOT / "agent") not in sys.path:
    sys.path.insert(0, str(ROOT / "agent"))
from orchestrator.comms import subject_hash  # noqa: E402

FORMAT = 1
SOURCES = ("observed", "declared", "inferred", "unknown")
CITING_SOURCES = ("declared", "inferred")
REQUIRED = ("application", "subject", "runtime", "facts")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

EXIT_REFUSED = 1
EXIT_UNREADABLE = 2


class ArtifactError(Exception):
    """A record that cannot be read at all. Always says what is missing."""


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses a duplicate key. PyYAML keeps the last one
    silently: w22's whoami record had two `facts:` sections, and its good
    facts would have vanished without a word."""


def _no_duplicates(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise ArtifactError(f"duplicate key {key!r} at line {key_node.start_mark.line + 1}: "
                                f"merge the two sections into one")
        seen.add(key)
    return loader.construct_mapping(node, deep=deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)


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
    max_port: int | None = None     # the name's final number is a port


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
            # fullmatch, not match: `$` also matches before a trailing newline,
            # so "listen:tcp/80\n" passed (w17 review).
            if not kind.pattern.fullmatch(name):
                return (f"{capability!r} does not match {kind_name} names "
                        f"({kind.pattern.pattern}); for example {kind.example}")
            if kind.max_port is not None:
                port = int(re.search(r"([0-9]+)$", name).group(1))
                if port > kind.max_port:
                    return f"{capability!r}: port {port} is above {kind.max_port}"
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
            max_port=raw.get("max_port"),
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
        data = yaml.load(path.read_text(), Loader=_StrictLoader)  # noqa: S506 — SafeLoader subclass
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
    for key in ("subject", "runtime"):
        if not isinstance(data[key], dict):
            raise ArtifactError(f"{path.name}: {key} must be a mapping")
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
        elif not str(ev["quote"]).strip():
            problems.append(f"{label}: evidence {n} quotes a blank line, which shows nothing")
        elif not isinstance(ev["line"], int) or ev["line"] < 1:
            problems.append(f"{label}: evidence {n} line {ev['line']!r} is not a line "
                            f"number (a positive integer)")
    return problems


def fact_problems(raw: dict, index: Index, *, runtime: bool = False) -> list[str]:
    """Every defect in one fact."""
    cap = raw.get("capability", "")
    if not isinstance(cap, str) or not cap:
        return [f"capability {cap!r}: give capability as a kind:name string"]
    label = cap
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
        if not isinstance(cap, str) or cap in observed:
            continue
        if source == "declared" and cap.startswith("listen:"):
            out.append(f"{cap}: declared only ({_cite(raw)}), never observed")
        elif source == "unknown":
            out.append(f"{cap}: unknown (looked at {', '.join(raw.get('looked_at') or [])})")
    return out


def _norm(text: str) -> str:
    return " ".join(str(text).split())


def quote_problems(raw: dict, subject: Path) -> list[str]:
    """Check each quote against the line it cites, in the staged subject.

    A citation is evidence only if the line says what the quote says. A model
    that paraphrases, or cites a file the application does not have, fails
    here — loudly, and with both strings, so it can correct itself.
    Whitespace is normalised; nothing else is.
    """
    label = raw.get("capability", "a fact")
    root = subject.resolve()
    problems = []
    for ev in raw.get("evidence") or []:
        if not isinstance(ev, dict) or not all(ev.get(k) for k in ("file", "line", "quote")):
            continue            # reported by _evidence_problems
        if not str(ev["quote"]).strip():
            continue            # likewise
        rel, line = str(ev["file"]), ev["line"]
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            problems.append(f"{label}: evidence cites {rel!r}, outside the subject; "
                            f"cite paths relative to the application root")
            continue
        if not target.is_file():
            problems.append(f"{label}: evidence cites {rel}, and the subject has no such file")
            continue
        if not isinstance(line, int):
            continue
        # Split on newline only: splitlines() also breaks on form feeds and
        # other separators, which made line numbers drift from `grep -n`.
        lines = target.read_text(encoding="utf-8", errors="replace").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        if line > len(lines):
            problems.append(f"{label}: evidence cites {rel}:{line}, and the file has only "
                            f"{len(lines)} lines")
            continue
        actual = lines[line - 1]
        if _norm(actual.rstrip("\r")) != _norm(ev["quote"]):
            problems.append(f"{label}: {rel}:{line} reads {actual.strip()!r}, not "
                            f"{str(ev['quote']).strip()!r} — quote the cited line exactly")
    return problems


def validate(path: str | Path, index: Index | None = None, *,
             subject: Path | None = None, allow_observed: bool = False) -> Report:
    """Validate a record. With `subject`, every quote is checked against the
    staged tree and the record's tree hash against that tree's.

    `observed` is refused unless `allow_observed=True`, which only observe.py
    passes, for records it wrote itself. The safe setting is the default: a
    caller that forgets the flag must not accept a stamped claim (w17 review).
    """
    index = index or load_index()
    artifact = load(path)
    report = Report(artifact=artifact)

    tree_hash = str(artifact.subject.get("tree_hash", ""))
    if not SHA256.match(tree_hash):
        report.problems.append(
            "subject.tree_hash is missing or not a sha256: it ties the record to the "
            "exact tree analysed (GitWorkspace.stage_subject returns it)")
    elif subject is not None:
        actual = subject_hash.tree_hash(subject)
        if actual != tree_hash:
            report.problems.append(
                f"subject.tree_hash {tree_hash[:12]} is not the staged subject's "
                f"({actual[:12]}): this record describes a different tree")

    everything = [(artifact.runtime, True), *((raw, False) for raw in artifact.facts)]
    for raw, is_runtime in everything:
        report.problems += fact_problems(raw, index, runtime=is_runtime)
        if not allow_observed and raw.get("source") == "observed":
            report.problems.append(
                f"{raw.get('capability')}: an agent may not write observed — only "
                f"observe.py may, from a run it watched. Use declared, inferred or unknown")
        if subject is not None and raw.get("source") in CITING_SOURCES:
            report.problems += quote_problems(raw, subject)
    report.assumptions = derive_assumptions(artifact)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--validate", metavar="FILE")
    ap.add_argument("--subject", metavar="DIR",
                    help="the staged application: quotes and tree_hash are checked against it")
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
        report = validate(args.validate, subject=Path(args.subject) if args.subject else None)
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
          f"{len(report.artifact.facts)} fact(s)"
          + ("" if args.subject else " — quotes NOT checked (no --subject)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
