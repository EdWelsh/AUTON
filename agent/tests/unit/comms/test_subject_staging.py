"""The subject application, staged read-only inside the workspace (A2).

The Analyst must read a repository AUTON did not write. A new read tool would be
a second traversal surface that has to re-earn what `_resolve` already proved,
so the subject is staged at `.auton/subject/` and the existing tools reach it.

One rule is added — nothing may write under `.auton/subject/` — and it takes
three layers, because agents hold a `shell` whose allowlist includes `python`
and `git`:

1. the file tools refuse the prefix, with a reason;
2. the files are read-only on disk, so a plain open-for-write fails;
3. a tree hash taken at staging is re-checked, so a change by *any* route
   (chmod, then write) is detected. This one is the gate.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "agent"))

from orchestrator.comms.git_workspace import SUBJECT_DIR, GitWorkspace, WorkspaceError  # noqa: E402
from orchestrator.comms.subject_hash import tree_hash  # noqa: E402

POSIX = pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes")


def _git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


@pytest.fixture
def subject(tmp_path):
    src = tmp_path / "app"
    (src / "pkg").mkdir(parents=True)
    (src / "app.py").write_text("import ssl\nprint('hi')\n")
    (src / "pkg" / "util.py").write_text("X = 1\n")
    (src / "run.sh").write_text("#!/bin/sh\n")
    (src / "run.sh").chmod(0o755)
    return src


@pytest.fixture
def ws(tmp_path):
    w = GitWorkspace(tmp_path / "ws")
    w.init()
    yield w
    w.unstage_subject()


# --------------------------------------------------------------------------- #
# Reading reaches it, unchanged tools
# --------------------------------------------------------------------------- #

def test_the_three_read_tools_reach_the_subject(ws, subject):
    ws.stage_subject(subject)
    assert ws.read_file(f"{SUBJECT_DIR}/app.py").startswith("import ssl")
    hits = ws.search_code("import ssl")
    assert any(h["file"] == f"{SUBJECT_DIR}/app.py" and h["line"] == 1 for h in hits)
    assert f"{SUBJECT_DIR}/pkg/util.py" in ws.list_files(SUBJECT_DIR, recursive=True)


def test_a_git_subject_is_exported_at_head_without_its_history(ws, subject):
    _git(subject, "init", "-q", "-b", "main")
    _git(subject, "add", "-A")
    _git(subject, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "c")
    (subject / "uncommitted.py").write_text("not at HEAD\n")
    ws.stage_subject(subject)
    staged = ws.path / SUBJECT_DIR
    assert (staged / "app.py").exists()
    assert not (staged / ".git").exists(), "history is not evidence"
    assert not (staged / "uncommitted.py").exists(), "HEAD is what was analysed"
    assert len(ws.subject_commit) == 40


# --------------------------------------------------------------------------- #
# Layer 1: the file tools refuse
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("path", [
    f"{SUBJECT_DIR}/app.py",
    f"{SUBJECT_DIR}/new.py",
    f"{SUBJECT_DIR}/../subject/app.py",
    f"./{SUBJECT_DIR}/pkg/util.py",
])
def test_write_file_under_the_subject_is_refused(ws, subject, path):
    ws.stage_subject(subject)
    with pytest.raises(WorkspaceError, match="evidence"):
        ws.write_file(path, "x")


def test_a_case_variant_is_refused_too(ws, subject):
    """macOS's default filesystem is case-insensitive: `.auton/SUBJECT/app.py`
    is the same file, and a string comparison would let it through."""
    ws.stage_subject(subject)
    variant = f"{SUBJECT_DIR.upper()}/app.py"
    if not (ws.path / variant).exists():
        pytest.skip("case-sensitive filesystem")
    with pytest.raises(WorkspaceError, match="evidence"):
        ws.write_file(variant, "x")


def test_edit_file_under_the_subject_is_refused(ws, subject):
    ws.stage_subject(subject)
    ws.read_file(f"{SUBJECT_DIR}/app.py")
    with pytest.raises(WorkspaceError, match="evidence"):
        ws.edit_file(f"{SUBJECT_DIR}/app.py", "import ssl", "import os")


def test_writing_elsewhere_still_works(ws, subject):
    ws.stage_subject(subject)
    ws.write_file("analysis/app.artifact.yaml", "format: 1\n")
    assert (ws.path / "analysis/app.artifact.yaml").exists()


# --------------------------------------------------------------------------- #
# Layer 2: read-only on disk
# --------------------------------------------------------------------------- #

@POSIX
def test_a_plain_open_for_write_fails(ws, subject):
    ws.stage_subject(subject)
    if os.geteuid() == 0:
        pytest.skip("root ignores mode bits")
    with pytest.raises(PermissionError):
        (ws.path / SUBJECT_DIR / "app.py").open("w")
    with pytest.raises(PermissionError):
        (ws.path / SUBJECT_DIR / "dropped.py").write_text("x")


@POSIX
def test_executable_bits_survive_staging(ws, subject):
    ws.stage_subject(subject)
    mode = (ws.path / SUBJECT_DIR / "run.sh").stat().st_mode
    assert mode & stat.S_IXUSR and not mode & stat.S_IWUSR


# --------------------------------------------------------------------------- #
# Layer 3: the hash is the gate
# --------------------------------------------------------------------------- #

def test_verify_passes_on_an_untouched_subject(ws, subject):
    digest = ws.stage_subject(subject)
    ws.verify_subject(digest)


@POSIX
def test_a_change_by_any_route_is_detected_and_named(ws, subject):
    """The shell route: `python -c "os.chmod(...); open(...,'w')"`."""
    digest = ws.stage_subject(subject)
    target = ws.path / SUBJECT_DIR / "pkg" / "util.py"
    target.chmod(0o644)
    target.write_text("X = 2\n")
    with pytest.raises(WorkspaceError) as exc:
        ws.verify_subject(digest)
    assert "pkg/util.py" in str(exc.value)


@POSIX
def test_an_added_file_is_detected(ws, subject):
    digest = ws.stage_subject(subject)
    d = ws.path / SUBJECT_DIR
    d.chmod(0o755)
    (d / "injected.py").write_text("x\n")
    with pytest.raises(WorkspaceError, match="injected.py"):
        ws.verify_subject(digest)


def test_the_hash_is_stable_and_byte_sensitive(tmp_path, subject):
    a = tree_hash(subject)
    assert tree_hash(subject) == a
    (subject / "app.py").write_text("import ssl\nprint('hi!')\n")
    assert tree_hash(subject) != a


def test_the_hash_is_the_same_before_and_after_staging(ws, subject):
    """Staging removes write bits; the hash must not depend on them, or every
    staged subject would fail its own check."""
    assert ws.stage_subject(subject) == tree_hash(subject)


# --------------------------------------------------------------------------- #
# Symlinks: staged as links, never followed
# --------------------------------------------------------------------------- #

@POSIX
def test_a_symlink_pointing_out_is_not_followed(ws, subject, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOKEN=hunter2\n")
    (subject / "leak.txt").symlink_to(secret)
    ws.stage_subject(subject)
    staged = ws.path / SUBJECT_DIR / "leak.txt"
    assert staged.is_symlink()
    with pytest.raises(WorkspaceError, match="outside"):
        ws.read_file(f"{SUBJECT_DIR}/leak.txt")
    assert not any("hunter2" in h["content"] for h in ws.search_code("TOKEN")), \
        "search_code must not read through a link out of the workspace"


# --------------------------------------------------------------------------- #
# Lifecycle and commits
# --------------------------------------------------------------------------- #

def test_restaging_is_refused(ws, subject):
    ws.stage_subject(subject)
    with pytest.raises(WorkspaceError, match="already staged"):
        ws.stage_subject(subject)


def test_unstage_removes_it(ws, subject):
    ws.stage_subject(subject)
    ws.unstage_subject()
    assert not (ws.path / SUBJECT_DIR).exists()


def test_the_subject_is_never_committed_onto_an_agent_branch(ws, subject):
    ws.stage_subject(subject)
    ws.create_branch("dev-01", "app", "001")
    ws.write_file("analysis/a.yaml", "x: 1\n")
    ws.commit("analysis")
    tracked = subprocess.run(["git", "-C", str(ws.path), "ls-files"], check=True,
                             capture_output=True, text=True).stdout
    assert "analysis/a.yaml" in tracked
    assert "subject" not in tracked


# --------------------------------------------------------------------------- #
# Scored by attempting one: every write route an agent has, through its real
# tool dispatcher, stopped by the layer named.
# --------------------------------------------------------------------------- #

def _agent(workspace: GitWorkspace):
    from unittest.mock import MagicMock

    from orchestrator.agents.base_agent import Agent, AgentRole
    from orchestrator.arch_registry import get_arch_profile
    return Agent(agent_id="analyst-01", role=AgentRole.DEVELOPER, system_prompt="t",
                 tools=[], client=MagicMock(), workspace=workspace,
                 message_bus=MagicMock(), kernel_spec_path=Path("/nonexistent"),
                 arch_profile=get_arch_profile("x86_64"))


async def test_file_tools_are_stopped_by_layer_one(ws, subject):
    ws.stage_subject(subject)
    agent = _agent(ws)
    out = await agent._execute_tool("write_file", {"path": f"{SUBJECT_DIR}/app.py",
                                                   "content": "evil"})
    assert "evidence" in out
    await agent._execute_tool("read_file", {"path": f"{SUBJECT_DIR}/app.py"})
    out = await agent._execute_tool("edit_file", {"path": f"{SUBJECT_DIR}/app.py",
                                                  "old": "import ssl", "new": "import os"})
    assert "evidence" in out
    assert (ws.path / SUBJECT_DIR / "app.py").read_text().startswith("import ssl")


@POSIX
async def test_a_shell_write_is_stopped_by_layer_two(ws, subject):
    if os.geteuid() == 0:
        pytest.skip("root ignores mode bits")
    digest = ws.stage_subject(subject)
    out = await _agent(ws)._execute_tool("shell", {
        "command": f"python3 -c \"open('{SUBJECT_DIR}/app.py','w').write('evil')\""})
    assert "PermissionError" in out, out
    ws.verify_subject(digest)


@POSIX
async def test_a_shell_chmod_then_write_is_caught_by_layer_three(ws, subject):
    digest = ws.stage_subject(subject)
    script = (f"import os; p='{SUBJECT_DIR}/app.py'; os.chmod(p, 0o644); "
              f"open(p,'w').write('evil')")
    await _agent(ws)._execute_tool("shell", {"command": f'python3 -c "{script}"'})
    assert (ws.path / SUBJECT_DIR / "app.py").read_text() == "evil", \
        "layers one and two are walked around by this route; that is the point"
    with pytest.raises(WorkspaceError, match="app.py"):
        ws.verify_subject(digest)
