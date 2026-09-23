"""Every markdown link between tracked files resolves.

This project refuses citations nobody can follow: the catalogue has a test that
its evidence paths are files git tracks, and `vendors.yaml` carries document
numbers with "verify it on the PDF's cover" beside them. Its own documentation
gets the same rule.

It was worth having. Moving 90 plans into `completed/` broke 34 links; another
28 had pointed at the wrong relative depth since before that, and two named a
PRD that had been deleted rather than archived. None of it was visible while
`.claude/` was gitignored, which is the other half of the rule: a citation to
a file the repository does not carry resolves for one person and nobody else.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LINK = re.compile(r"\]\(([^)\s]+\.md)\)")


def tracked_files() -> set[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                         capture_output=True, text=True, check=True)
    return set(out.stdout.split())


def markdown_files() -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "*.md"],
                         capture_output=True, text=True, check=True)
    return out.stdout.split()


def test_every_markdown_link_points_at_a_tracked_file():
    tracked = tracked_files()
    broken: list[str] = []
    checked = 0
    for name in markdown_files():
        path = ROOT / name
        for match in LINK.finditer(path.read_text(errors="replace")):
            target = match.group(1)
            if target.startswith(("http", "#")):
                continue
            try:
                rel = (path.parent / target).resolve().relative_to(ROOT)
            except ValueError:
                continue            # outside the repo; not this test's business
            checked += 1
            if str(rel) not in tracked:
                broken.append(f"{name} -> {target}")
    assert checked > 100, "the link check found almost nothing to check"
    assert not broken, "links to files the repository does not carry:\n  " + "\n  ".join(broken)


def test_the_research_record_is_tracked():
    """docs/ cites reports under .claude/PRPs; a reader must be able to open
    them. The rest of .claude stays ignored."""
    tracked = tracked_files()
    assert any(f.startswith(".claude/PRPs/reports/") for f in tracked)
    assert any(f.startswith(".claude/PRPs/prds/") for f in tracked)
    assert ".claude/settings.local.json" not in tracked, "local settings stay local"
