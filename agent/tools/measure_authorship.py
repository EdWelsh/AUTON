"""Measure what authoring a subject cost, the same way for a control and an experiment.

    python agent/tools/measure_authorship.py --subject dhcp
    python agent/tools/measure_authorship.py --subject tftp --root <workspace>
    scripts/measure_authorship.sh --service dhcp        # the plans' spelling

F6, V8 and H7 compare an agent's cost against a human control. Hand counts made
once per phase do not compare: re-counting three published controls from their
own artifacts found three that differ. So the counting rules live here, once:

- **lines** are physical lines (`wc -l`).
- **spec lines** are lines *written*: a whole file, a `###` section, or a
  section's growth over a base revision when the author extended one.
- **test cases** are `ok(...)` call sites, excluding the helper's definition.
  Counted statically because a control's test may no longer compile (F4's
  server.c exists only as structure in the reference graph).
- **reference lines** are split into new and reused. V6 found that ratio was the
  one that mattered; counting reused lines as written flatters.

Measured figures are printed beside the recorded ones, with the difference.
Nothing here decides pass or fail. The gates do that.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUBJECTS = Path(__file__).resolve().parent / "authorship.yaml"

OK_CALL = re.compile(r"\bok\(")
OK_DEFINITION = re.compile(r"^\s*(static\s+)?(void|int)\s+ok\(")
SECTION_HEADING = re.compile(r"^#{1,3} ")


@dataclass
class Row:
    subject: str
    role: str
    measured: dict[str, object] = field(default_factory=dict)
    recorded: dict[str, object] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    note: str = ""


def load_subjects(path: Path = SUBJECTS) -> dict[str, dict]:
    import yaml

    return yaml.safe_load(path.read_text())["subjects"]


def read_text(root: Path, path: str, rev: str | None = None) -> str | None:
    """A file's text from the working tree, or from git at `rev`. None if absent."""
    if rev:
        r = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{path}"],
                           capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None
    p = root / path
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None


def line_count(text: str) -> int:
    return text.count("\n") + (0 if text.endswith("\n") or not text else 1)


def section(text: str, heading: str) -> str | None:
    """The body of the markdown section whose heading ends with `heading`, up to
    the next heading at the same or a higher level."""
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if SECTION_HEADING.match(line) and line.strip().lstrip("#").strip() == heading:
            level = len(line) - len(line.lstrip("#"))
            end = next((j for j in range(i + 1, len(lines))
                        if SECTION_HEADING.match(lines[j])
                        and len(lines[j]) - len(lines[j].lstrip("#")) <= level),
                       len(lines))
            return "".join(lines[i:end])
    return None


def spec_lines(root: Path, spec: dict) -> int | None:
    # `in_repo`: the spec is read from the repo (read_spec), not from the
    # experiment's workspace. Since w12 no spec is copied into a workspace.
    text = read_text(ROOT if spec.get("in_repo") else root, spec["path"], spec.get("rev"))
    if text is None:
        return None
    if "section" not in spec:
        return line_count(text)
    body = section(text, spec["section"])
    if body is None:
        return None
    written = line_count(body)
    if spec.get("base_rev"):
        base = read_text(root, spec["path"], spec["base_rev"])
        base_body = section(base, spec["section"]) if base else None
        written -= line_count(base_body) if base_body else 0
    return written


def count_cases(text: str) -> int:
    return sum(1 for line in text.splitlines()
               if OK_CALL.search(line) and not OK_DEFINITION.match(line))


def graph_lines(graph: dict) -> tuple[int | None, list[str]]:
    text = read_text(ROOT, graph["path"], graph.get("rev"))
    if text is None:
        return None, []
    files = [f for f in json.loads(text)["files"] if f["subsystem"] == graph["subsystem"]]
    if not files:
        return None, []
    return sum(f["lines"] for f in files), [f"{f['path']} {f['lines']}" for f in files]


def added_lines(before: str, after: str) -> int:
    """Lines present in `after` and not in `before`: what an author wrote into a
    file they were given."""
    return sum(1 for d in difflib.ndiff(before.splitlines(), after.splitlines())
               if d.startswith("+ "))


def measure(name: str, subject: dict, root: Path) -> Row:
    row = Row(subject=name, role=subject.get("role", ""),
              recorded=dict(subject.get("recorded") or {}),
              note=" ".join((subject.get("note") or "").split()))
    m = row.measured

    if "spec" in subject:
        n = spec_lines(root, subject["spec"])
        if n is None:
            where = subject["spec"]["path"]
            if subject["spec"].get("section"):
                where = f"section {subject['spec']['section']!r} in {where}"
            row.missing.append(f"spec {where}")
        m["spec_lines"] = n
        if subject["spec"].get("authored_by"):
            m["spec_authored_by"] = subject["spec"]["authored_by"]

    impl = subject.get("implementation") or {}
    if "graph" in impl:
        n, detail = graph_lines(impl["graph"])
        m["implementation_lines"] = n
        m["implementation_files"] = detail
        if n is None:
            row.missing.append("implementation (graph)")
    elif "files" in impl:
        texts = {p: read_text(root, p) for p in impl["files"]}
        row.missing += [f"implementation {p}" for p, t in texts.items() if t is None]
        m["implementation_lines"] = sum(line_count(t) for t in texts.values() if t)
        m["implementation_files"] = [f"{p} {line_count(t)}" for p, t in texts.items() if t]
    elif subject.get("kind") == "mitigation":
        m["implementation_lines"] = 0

    if "record" in subject:
        m["record_present"] = read_text(root, subject["record"]) is not None

    new = [read_text(root, p) for p in subject.get("reference_new", [])]
    if subject.get("reference_new"):
        m["reference_new_lines"] = sum(line_count(t) for t in new if t)
    reused = subject.get("reference_reused", [])
    if reused:
        m["reference_reused_lines"] = sum(line_count(read_text(root, p) or "") for p in reused)
        if root != ROOT:
            # A reused file the author edited is partly written, and the edit counts.
            m["reference_edited_lines"] = sum(
                added_lines(read_text(ROOT, p) or "", read_text(root, p) or "") for p in reused)

    tests = subject.get("tests", [])
    if tests:
        texts = [read_text(root, t["path"], t.get("rev")) for t in tests]
        row.missing += [f"test {t['path']}" for t, x in zip(tests, texts) if x is None]
        m["test_lines"] = sum(line_count(x) for x in texts if x)
        m["test_cases"] = sum(count_cases(x) for x in texts if x)
    return row


def render(row: Row) -> str:
    out = [f"{row.subject} — {row.role}"]
    keys = list(dict.fromkeys([*row.measured, *row.recorded]))
    for k in keys:
        got, want = row.measured.get(k), row.recorded.get(k)
        if isinstance(got, list):
            out.append(f"  {k:<24}")
            out += [f"      {g}" for g in got]
            continue
        mark = ""
        if want is not None and got is not None and got != want:
            mark = f"   (recorded {want}; differs by {got - want:+d})" if isinstance(got, int) \
                   and isinstance(want, int) else f"   (recorded {want})"
        elif want is not None and got is None:
            mark = f"   (recorded {want}; not measurable from artifacts)"
        out.append(f"  {k:<24} {'—' if got is None else got}{mark}")
    for miss in row.missing:
        out.append(f"  MISSING {miss}")
    if row.note:
        out.append(f"  note: {row.note}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    who = ap.add_mutually_exclusive_group(required=True)
    for flag in ("subject", "service", "driver", "mitigation"):
        who.add_argument(f"--{flag}", metavar="NAME")
    ap.add_argument("--root", type=Path, default=ROOT,
                    help="where the subject's paths live (an experiment's workspace)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    name = args.subject or args.service or args.driver or args.mitigation
    subjects = load_subjects()
    if name not in subjects:
        print(f"unknown subject {name!r}; known: {', '.join(subjects)}", file=sys.stderr)
        return 2
    row = measure(name, subjects[name], args.root.resolve())
    if args.json:
        print(json.dumps(row.__dict__, indent=2, default=str))
    else:
        print(render(row))
    return 1 if row.missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
