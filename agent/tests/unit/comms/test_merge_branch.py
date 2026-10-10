"""merge_branch survives a merge git refuses before starting (w23: R10's run died on it)."""
import subprocess

from orchestrator.comms.git_workspace import GitWorkspace, untracked_blockers

G = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]


def _git(path, *a):
    subprocess.run([*G, "-C", str(path), *a], check=True, capture_output=True)


def _repo(tmp_path):
    ws = GitWorkspace(tmp_path)
    ws.init()
    (tmp_path / "a.txt").write_text("a")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "base")
    return ws


def test_the_blockers_are_read_from_gits_message():
    msg = ("error: The following untracked working tree files would be overwritten by merge:\n"
           "\tbuild/log.txt\n\tout.o\nPlease move or remove them before you merge.\n")
    assert untracked_blockers(msg) == ["build/log.txt", "out.o"]
    assert untracked_blockers("CONFLICT (content)") == []


def test_untracked_debris_in_main_does_not_block_the_merge(tmp_path):
    ws = _repo(tmp_path)
    _git(tmp_path, "checkout", "-b", "agent/x")
    (tmp_path / "build.log").write_text("from the branch")
    _git(tmp_path, "add", "build.log")
    _git(tmp_path, "commit", "-m", "adds a log")
    _git(tmp_path, "checkout", "main")
    (tmp_path / "build.log").write_text("debris left in main")      # untracked here
    assert ws.merge_branch("agent/x") is True
    assert (tmp_path / "build.log").read_text() == "from the branch"


def test_a_real_conflict_returns_false_and_leaves_main_clean(tmp_path):
    ws = _repo(tmp_path)
    _git(tmp_path, "checkout", "-b", "agent/y")
    (tmp_path / "a.txt").write_text("branch")
    _git(tmp_path, "commit", "-am", "branch edit")
    _git(tmp_path, "checkout", "main")
    (tmp_path / "a.txt").write_text("main")
    _git(tmp_path, "commit", "-am", "main edit")
    assert ws.merge_branch("agent/y") is False
    assert (tmp_path / "a.txt").read_text() == "main"
