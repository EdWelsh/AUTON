"""The wiki's source (wiki/) has no broken page links, and its generated pages match the data.

scripts/wiki.py builds the Specialists page and the numbers on Home from the
data they restate; this fails when the data moved and the wiki did not.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_the_wiki_checks_clean():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "wiki.py"), "check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_page_is_in_the_sidebar():
    sidebar = (ROOT / "wiki" / "_Sidebar.md").read_text()
    pages = {p.stem for p in (ROOT / "wiki").glob("*.md") if not p.stem.startswith("_")}
    missing = [p for p in pages if f"({p})" not in sidebar and f"[[{p}]]" not in sidebar]
    assert not missing, f"pages missing from the sidebar: {missing}"
