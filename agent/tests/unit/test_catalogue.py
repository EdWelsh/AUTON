"""The catalogue keeps AUTON's claims honest (factory F12).

`roles.c` used to promise things in prose ("needs persistent storage and a
query engine") that went stale the moment a service landed, and could not say
the answer that is now usually true: this image does not do it, and a dedicated
AUTON image does. The catalogue is data, and these are its rules.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from gen_roles import CatalogueError, generate, load  # noqa: E402

CATALOGUE = ROOT / "agent" / "kernel_spec" / "catalogue.yaml"
SERVICES = ROOT / "agent" / "kernel_spec" / "services"


def test_every_row_cites_evidence_that_exists():
    for row in load(CATALOGUE):
        for path in row["evidence"]:
            assert (ROOT / path).exists(), \
                f"{row['name']} cites {path}, which is not there"


def _is_tracked(path: str) -> bool:
    """git ls-files knows; an ignored path would vanish from a clone."""
    import subprocess

    r = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", path],
                       capture_output=True)
    return r.returncode != 0


def test_every_roadmap_row_names_what_blocks_it():
    for row in load(CATALOGUE):
        if row["status"] != "roadmap":
            continue
        blocker = ROOT / row["blocked_by"]
        assert blocker.exists(), f"{row['name']} is blocked by {row['blocked_by']}, missing"


def test_no_row_cites_a_file_a_clone_would_not_have():
    """The plans live under .claude/, which is gitignored. Citing one is a
    phantom citation: it resolves here and nowhere else."""
    for row in load(CATALOGUE):
        cited = list(row["evidence"]) + ([row["blocked_by"]] if row.get("blocked_by") else [])
        for path in cited:
            assert _is_tracked(path), \
                f"{row['name']} cites {path}, which git ignores: a clone would not have it"


def test_every_shipped_service_spec_has_a_row():
    """A service that exists and is not in the catalogue is a capability the
    chat will deny having."""
    names = {p.stem for p in SERVICES.glob("*.md")} - {"README"}
    evidence = {path for row in load(CATALOGUE) for path in row["evidence"]}
    for name in names:
        assert any(f"services/{name}.md" in e for e in evidence), \
            f"{name}.md ships but no catalogue row cites it"


def test_a_row_without_evidence_is_refused(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("roles:\n  - keyword: [x]\n    name: x\n    status: roadmap\n    note: n\n")
    with pytest.raises(CatalogueError, match="evidence"):
        load(p)


def test_a_roadmap_row_may_not_say_coming_soon(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("roles:\n  - keyword: [x]\n    name: x\n    status: roadmap\n"
                 "    note: coming soon\n    evidence: README.md\n")
    with pytest.raises(CatalogueError, match="cite what blocks it"):
        load(p)


def test_a_dedicated_row_must_say_how_to_build_it(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("roles:\n  - keyword: [x]\n    name: x\n    status: dedicated-image\n"
                 "    note: n\n    evidence: README.md\n")
    with pytest.raises(CatalogueError, match="how to build"):
        load(p)


def test_a_duplicate_keyword_is_refused(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("roles:\n"
                 "  - {keyword: [x], name: a, status: host-only, note: n, evidence: README.md}\n"
                 "  - {keyword: [x], name: b, status: host-only, note: n, evidence: README.md}\n")
    with pytest.raises(CatalogueError, match="twice"):
        load(p)


class TestTheActionPointer:
    """The rule that keeps [ABSENT] from impersonating a service."""

    def test_an_in_image_role_gets_its_action(self):
        c = generate(load(CATALOGUE), {"http_server_run"})
        assert '"web", "web server", CAP_IN_IMAGE' in c
        assert "http_server_run }" in c

    def test_an_in_image_role_absent_from_the_slice_gets_none(self):
        c = generate(load(CATALOGUE), set())
        assert "dns_server_run" not in c, \
            "a pointer to an absent symbol resolves to the [ABSENT] stub"
        assert "void http_server_run(void);" not in c

    def test_a_dedicated_role_never_gets_an_action(self):
        c = generate(load(CATALOGUE), {"http_server_run", "smtp_serve"})
        for line in c.splitlines():
            if "CAP_DEDICATED" in line:
                continue
        dedicated = [i for i, line in enumerate(c.splitlines()) if "CAP_DEDICATED" in line]
        assert dedicated
        for i in dedicated:
            assert c.splitlines()[i + 1].rstrip().endswith("0 },"), \
                "a dedicated-image row must have action = 0"

    def test_a_dedicated_role_tells_the_user_what_to_build(self):
        c = generate(load(CATALOGUE), set())
        assert "a dedicated AUTON image does this: auton build smtp" in c

    def test_a_roadmap_role_says_it_is_not_built(self):
        c = generate(load(CATALOGUE), set())
        assert "not built:" in c


def test_the_database_row_no_longer_promises_a_query_engine():
    """The specific stale promise this replaces: roles.c said a database needs
    'persistent storage and a query engine', and the KV store has neither SQL
    nor a query engine by design."""
    rows = {r["name"]: r for r in load(CATALOGUE)}
    kv = rows["key-value store"]
    assert "query engine" not in kv["note"] or "no query engine" in kv["note"]
    assert "Not SQL" in kv["note"]
