"""What an agent is allowed to write, and where.

This is the defect that stopped three phases across three PRDs. From
`.claude/PRPs/prds/README.md`: *"The loop can dispatch, but an architect
overwrote `net.h` with a placeholder. Workspace isolation and write granularity
come first."*

Reproduced before the fix, and worse than the note said:

    1. clobber:    net.h 155 bytes -> 24 bytes, silently
    2. traversal:  ../escaped.txt  -> escaped to the workspace's parent
    3. absolute:   /tmp/probe.txt  -> wrote outside the workspace entirely

The third is not a correctness bug. `write_file` is held by five agent roles.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "agent"))

from orchestrator.comms.git_workspace import (  # noqa: E402
    GitWorkspace,
    WorkspaceError,
)

HEADER = "/* 200 lines of real header */\n" * 5


@pytest.fixture
def ws(tmp_path):
    w = GitWorkspace(tmp_path / "repo")
    w.path.mkdir(parents=True, exist_ok=True)
    return w


class TestTheIncident:
    """The regression test for the thing that actually happened. A defect with
    no test is an intention, and this one has been quoted in the PRD index long
    enough to become folklore."""

    def test_an_architect_cannot_replace_a_header_it_never_read(self, ws):
        (ws.path / "net.h").write_text(HEADER)

        with pytest.raises(WorkspaceError, match="has not read"):
            ws.write_file("net.h", "/* TODO: placeholder */\n")

    def test_the_header_survives_intact(self, ws):
        (ws.path / "net.h").write_text(HEADER)
        with pytest.raises(WorkspaceError):
            ws.write_file("net.h", "/* TODO */\n")

        assert (ws.path / "net.h").read_text() == HEADER

    def test_the_refusal_says_what_to_do_instead(self, ws):
        """An agent that cannot tell why it was refused retries the same
        thing."""
        (ws.path / "net.h").write_text(HEADER)

        with pytest.raises(WorkspaceError) as exc:
            ws.write_file("net.h", "x")

        assert "read_file" in str(exc.value)
        assert "edit_file" in str(exc.value)


class TestContainment:
    def test_an_absolute_path_is_refused(self, ws, tmp_path):
        """`Path(root) / "/tmp/x"` is `/tmp/x` — an absolute path does not join,
        it replaces, so the workspace root is silently discarded."""
        outside = tmp_path / "outside.txt"

        with pytest.raises(WorkspaceError, match="absolute path"):
            ws.write_file(str(outside), "escaped\n")

        assert not outside.exists()

    def test_traversal_is_refused(self, ws):
        with pytest.raises(WorkspaceError, match="outside the workspace"):
            ws.write_file("../escaped.txt", "escaped\n")

        assert not (ws.path.parent / "escaped.txt").exists()

    def test_deep_traversal_is_refused(self, ws):
        with pytest.raises(WorkspaceError, match="outside the workspace"):
            ws.write_file("a/b/../../../escaped.txt", "escaped\n")

    def test_a_symlink_out_of_the_workspace_is_refused(self, ws, tmp_path):
        """A string check on `..` does not catch this, which is why the resolved
        result is what gets compared."""
        target = tmp_path / "elsewhere"
        target.mkdir()
        (ws.path / "link").symlink_to(target)

        with pytest.raises(WorkspaceError, match="outside the workspace"):
            ws.write_file("link/escaped.txt", "escaped\n")

        assert not (target / "escaped.txt").exists()

    def test_reading_is_contained_too(self, ws):
        """A guard on one caller leaves the others. `read_file`, `list_files`
        and `edit_file` all take paths."""
        with pytest.raises(WorkspaceError):
            ws.read_file("../../etc/passwd")

    def test_listing_is_contained_too(self, ws):
        with pytest.raises(WorkspaceError):
            ws.list_files("..")

    def test_editing_is_contained_too(self, ws):
        with pytest.raises(WorkspaceError):
            ws.edit_file("/etc/hosts", "a", "b")

    def test_a_normal_relative_path_still_works(self, ws):
        ws.write_file("kernel/net/e1000.c", "int x;\n")

        assert (ws.path / "kernel" / "net" / "e1000.c").read_text() == "int x;\n"


class TestCreatingIsStillFree:
    def test_a_new_file_needs_no_read(self, ws):
        """A rule that makes every write a read-first ceremony gets worked
        around by agents writing to new paths."""
        ws.write_file("brand/new.c", "int main(void){return 0;}\n")

        assert (ws.path / "brand" / "new.c").exists()

    def test_parent_directories_are_still_created(self, ws):
        ws.write_file("a/b/c/d.c", "x\n")

        assert (ws.path / "a" / "b" / "c" / "d.c").exists()

    def test_reading_then_overwriting_is_allowed(self, ws):
        """Deliberate replacement is legitimate. What is refused is doing it
        sight-unseen."""
        (ws.path / "net.h").write_text(HEADER)
        ws.read_file("net.h")

        ws.write_file("net.h", "/* deliberately replaced */\n")

        assert "deliberately" in (ws.path / "net.h").read_text()

    def test_a_file_this_workspace_wrote_counts_as_seen(self, ws):
        """Otherwise an agent cannot revise what it just created."""
        ws.write_file("draft.c", "v1\n")
        ws.write_file("draft.c", "v2\n")

        assert (ws.path / "draft.c").read_text() == "v2\n"


class TestEditFile:
    def test_an_edit_matching_once_applies(self, ws):
        ws.write_file("x.c", "int old_name(void) { return 1; }\n")

        ws.edit_file("x.c", "old_name", "new_name")

        assert "new_name" in (ws.path / "x.c").read_text()

    def test_an_edit_matching_nothing_is_refused(self, ws):
        """A match count of zero means the agent is working from a stale
        assumption. Applied blindly that is silent corruption."""
        ws.write_file("x.c", "int a;\n")

        with pytest.raises(WorkspaceError, match="matched nothing"):
            ws.edit_file("x.c", "int b;", "int c;")

    def test_an_edit_matching_twice_is_refused(self, ws):
        """More than one match means the agent does not know which it is
        changing."""
        ws.write_file("x.c", "int a;\nint a;\n")

        with pytest.raises(WorkspaceError, match="matched 2 times"):
            ws.edit_file("x.c", "int a;", "int b;")

    def test_that_refusal_says_how_to_disambiguate(self, ws):
        ws.write_file("x.c", "a\na\n")

        with pytest.raises(WorkspaceError) as exc:
            ws.edit_file("x.c", "a", "b")

        assert "surrounding text" in str(exc.value)

    def test_a_failed_edit_changes_nothing(self, ws):
        ws.write_file("x.c", "int a;\nint a;\n")
        before = (ws.path / "x.c").read_text()

        with pytest.raises(WorkspaceError):
            ws.edit_file("x.c", "int a;", "int b;")

        assert (ws.path / "x.c").read_text() == before

    def test_editing_a_missing_file_is_a_file_error(self, ws):
        with pytest.raises(FileNotFoundError):
            ws.edit_file("nope.c", "a", "b")

    def test_an_edit_does_not_need_a_prior_read(self, ws, tmp_path):
        """An edit names the text it replaces, which is the evidence a blind
        write lacks. Requiring a read as well would add ceremony without adding
        safety."""
        (ws.path / "y.c").write_text("int keep_me;\nint change_me;\n")

        ws.edit_file("y.c", "change_me", "changed")

        assert "keep_me" in (ws.path / "y.c").read_text()


class TestTheToolSurface:
    def test_every_role_that_writes_can_also_edit(self):
        """An agent offered only whole-file replacement will use it for partial
        changes, which is the incident."""
        from orchestrator.llm.tools import (
            ARCHITECT_TOOLS,
            DATA_SCIENTIST_TOOLS,
            DEVELOPER_TOOLS,
            INTEGRATOR_TOOLS,
            TESTER_TOOLS,
        )

        for tools in (ARCHITECT_TOOLS, DEVELOPER_TOOLS, TESTER_TOOLS,
                      INTEGRATOR_TOOLS, DATA_SCIENTIST_TOOLS):
            names = {t["function"]["name"] for t in tools}
            assert ("edit_file" in names) == ("write_file" in names)

    def test_the_reviewer_can_do_neither(self):
        from orchestrator.llm.tools import REVIEWER_TOOLS

        names = {t["function"]["name"] for t in REVIEWER_TOOLS}
        assert "write_file" not in names and "edit_file" not in names

    def test_write_files_description_points_at_edit(self):
        """The description is the only thing steering the choice at the moment
        the agent makes it."""
        from orchestrator.llm.tools import TOOL_WRITE_FILE

        assert "edit_file" in TOOL_WRITE_FILE["function"]["description"]

    def test_edit_files_description_says_exactly_once(self):
        from orchestrator.llm.tools import TOOL_EDIT_FILE

        assert "exactly once" in TOOL_EDIT_FILE["function"]["description"]
