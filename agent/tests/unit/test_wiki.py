"""The wiki's source (wiki/) has no broken page links, and its generated pages match the data.

scripts/wiki.py builds the Specialists page and the numbers on Home from the
data they restate; this fails when the data moved and the wiki did not.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("wiki_tool", ROOT / "scripts" / "wiki.py")
wiki = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wiki)


def test_the_wiki_checks_clean():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "wiki.py"), "check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_page_is_in_the_sidebar():
    sidebar = (ROOT / "wiki" / "_Sidebar.md").read_text()
    pages = {p.stem for p in (ROOT / "wiki").glob("*.md") if not p.stem.startswith("_")}
    missing = [p for p in pages if f"({p})" not in sidebar and f"[[{p}]]" not in sidebar]
    assert not missing, f"pages missing from the sidebar: {missing}"


def test_stale_numbers_on_home_fail_the_check(tmp_path, monkeypatch, capsys):
    copy = tmp_path / "wiki"
    shutil.copytree(ROOT / "wiki", copy)
    monkeypatch.setattr(wiki, "WIKI", copy)
    # The copy, current with today's data (build() itself reports paths under ROOT).
    (copy / "Specialists.md").write_text(wiki.specialists_page())
    home = (copy / "Home.md").read_text()
    a, b = wiki.numbers_span(home)
    block = "\n" + wiki.numbers_block()
    home = home[:a] + block + home[b:]
    (copy / "Home.md").write_text(home)
    a, b = wiki.numbers_span(home)
    assert wiki.check() == 0
    stale = block.replace("Specialist agents | **", "Specialist agents | **9")
    assert stale != block
    (copy / "Home.md").write_text(home[:a] + stale + home[b:])
    assert wiki.check() == 1
    assert "Home.md is stale" in capsys.readouterr().out
