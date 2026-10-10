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


def test_commit_pending_works_when_build_is_gitignored(tmp_path):
    """R3 died at iteration 0: `git add -A -- . :(exclude)build` exits 1 when build is ignored."""
    ws = _repo(tmp_path)
    (tmp_path / ".gitignore").write_text("build\n")
    _git(tmp_path, "add", ".gitignore")
    _git(tmp_path, "commit", "-m", "ignore build")
    branch = ws.create_branch("dev-01", "mm", "pmm")
    (tmp_path / "pmm.c").write_text("int x;")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "o").write_text("obj")
    assert ws.commit_pending(branch, "work") is True
    names = subprocess.run(["git", "-C", str(tmp_path), "show", "--name-only", "--format=", "HEAD"],
                           capture_output=True, text=True).stdout.split()
    assert names == ["pmm.c"]


def test_engine_state_is_never_committed_and_never_blocks_leaving_a_branch(tmp_path):
    """R6, R10, R11, R12 died on `git checkout main`: .auton/tasks/<id>.json was tracked and dirty."""
    ws = _repo(tmp_path)
    branch = ws.create_branch("dev-01", "mm", "pmm")
    (tmp_path / ".auton" / "tasks").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".auton" / "tasks" / "t1.json").write_text("{}")
    (tmp_path / "pmm.c").write_text("int x;")
    ws.commit("work")                                   # the unfiltered path, used to add -A
    tracked = subprocess.run(["git", "-C", str(tmp_path), "ls-files"], capture_output=True, text=True).stdout
    assert ".auton" not in tracked and "pmm.c" in tracked
    # a tracked engine-state file that is dirty must not stop checkout of main
    _git(tmp_path, "add", "-f", ".auton/tasks/t1.json")
    _git(tmp_path, "commit", "-m", "someone tracked it")
    (tmp_path / ".auton" / "tasks" / "t1.json").write_text('{"status": "review"}')
    ws.checkout_main()
    assert ws.repo.active_branch.name == "main"
    assert branch != "main"
