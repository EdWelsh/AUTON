"""Specialist agents: one per aspect of kernel creation (kernel_spec/specialists.yaml).

A specialist is a Developer whose prompt carries one area's knowledge, its specs
and its review checklist; the manager assigns it work by pool name
("memory_specialist"). The same checklist is given to the reviewer for any
change that touches the specialist's files, so an area's pitfalls are checked
whether or not its specialist wrote the code.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

import yaml

from orchestrator.agents.base_agent import SPEC_KINDS
from orchestrator.agents.developer_agent import DeveloperAgent

SPECIALISTS = Path(__file__).resolve().parents[2] / "kernel_spec" / "specialists.yaml"


class SpecialistError(Exception):
    pass


@dataclass(frozen=True)
class Specialty:
    id: str
    title: str
    specs: tuple[str, ...]
    files: tuple[str, ...]
    focus: str
    checklist: tuple[str, ...]

    @property
    def pool(self) -> str:
        return f"{self.id.replace('-', '_')}_specialist"

    def covers(self, path: str) -> bool:
        return any(fnmatch.fnmatch(path, g) for g in self.files)

    def prompt_section(self) -> str:
        items = "\n".join(f"- {c}" for c in self.checklist)
        return (f"\n\n## Your specialty: {self.title}\n{self.focus}\n\n"
                f"Read these specs before you write code: {', '.join(self.specs)}.\n"
                f"Your work will be reviewed against this checklist, so meet it:\n{items}\n")


def spec_path(name: str, root: Path) -> Path:
    """The file a read_spec name resolves to (mirrors Agent._read_spec)."""
    if name == "architecture":
        return root / "architecture.md"
    if name == "hal":
        return root / "arch" / "hal.md"
    if "/" in name:
        kind, rest = name.split("/", 1)
        if kind not in SPEC_KINDS:
            raise SpecialistError(f"spec {name!r}: kind {kind!r} not one of {SPEC_KINDS}")
        return root / kind / f"{rest}.md"
    return root / "subsystems" / f"{name}.md"


def load(path: Path = SPECIALISTS, spec_root: Path | None = None) -> tuple[Specialty, ...]:
    spec_root = spec_root or path.parent
    data = yaml.safe_load(path.read_text())
    out, seen = [], set()
    for raw in data.get("specialists", []):
        for f in ("id", "title", "specs", "files", "focus", "checklist"):
            if not raw.get(f):
                raise SpecialistError(f"specialist {raw.get('id', '?')}: missing {f!r}")
        if raw["id"] in seen:
            raise SpecialistError(f"specialist {raw['id']!r} appears twice")
        seen.add(raw["id"])
        for s in raw["specs"]:
            if not spec_path(s, spec_root).is_file():
                raise SpecialistError(f"specialist {raw['id']}: spec {s!r} does not exist "
                                      f"({spec_path(s, spec_root)})")
        out.append(Specialty(id=raw["id"], title=raw["title"], specs=tuple(raw["specs"]),
                             files=tuple(raw["files"]), focus=" ".join(raw["focus"].split()),
                             checklist=tuple(raw["checklist"])))
    return tuple(out)


def select(specialties: tuple[Specialty, ...], wanted) -> tuple[Specialty, ...]:
    """`wanted` from config: true/"all" for every one, or a list of ids."""
    if wanted is True or wanted == "all":
        return specialties
    if not wanted:
        return ()
    ids = {s.id for s in specialties}
    unknown = [w for w in wanted if w not in ids]
    if unknown:
        raise SpecialistError(f"unknown specialists {unknown}; known: {sorted(ids)}")
    return tuple(s for s in specialties if s.id in set(wanted))


def checklists_for(changed: list[str], specialties: tuple[Specialty, ...]) -> str:
    """The review checklists of every specialty whose files a change touches."""
    hit = [s for s in specialties if any(s.covers(f) for f in changed)]
    if not hit:
        return ""
    parts = ["\n## Specialist checklists for the files this change touches"]
    for s in hit:
        files = [f for f in changed if s.covers(f)]
        parts.append(f"\n### {s.title} ({', '.join(files[:6])})")
        parts += [f"- {c}" for c in s.checklist]
    parts.append("\nA checklist item the change violates is an issue; cite the line.")
    return "\n".join(parts) + "\n"


class SpecialistAgent(DeveloperAgent):
    """A Developer with one area's knowledge and checklist in its prompt."""

    def __init__(self, specialty: Specialty, **kwargs):
        super().__init__(**kwargs)
        self.specialty = specialty
        self.system_prompt = self.system_prompt + specialty.prompt_section()
