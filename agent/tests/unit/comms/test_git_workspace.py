"""Tests for git workspace management."""

import pytest

from orchestrator.comms.git_workspace import GitWorkspace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path):
    """Create and initialize a GitWorkspace in a temporary directory."""
    ws = GitWorkspace(tmp_path / "repo")
    ws.init()
    return ws


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

class TestInit:
    def test_init_creates_repo_in_empty_dir(self, tmp_path):
        ws = GitWorkspace(tmp_path / "new_repo")
        ws.init()
        assert (ws.path / ".git").is_dir()

    def test_init_creates_readme(self, tmp_path):
        ws = GitWorkspace(tmp_path / "new_repo")
        ws.init()
        assert (ws.path / "README.md").exists()

    def test_init_creates_auton_metadata_dirs(self, tmp_path):
        ws = GitWorkspace(tmp_path / "new_repo")
        ws.init()
        assert (ws.path / ".auton" / "tasks").is_dir()
        assert (ws.path / ".auton" / "messages").is_dir()

    def test_init_creates_initial_commits(self, tmp_path):
        ws = GitWorkspace(tmp_path / "new_repo")
        ws.init()
        commits = list(ws.repo.iter_commits())
        assert len(commits) >= 2  # initial + .auton metadata

    def test_init_opens_existing_repo(self, workspace):
        # Re-init on the same path should open, not re-create
        ws2 = GitWorkspace(workspace.path)
        ws2.init()
        assert ws2.repo is not None

    def test_repo_property_raises_before_init(self, tmp_path):
        ws = GitWorkspace(tmp_path / "uninit")
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = ws.repo


# ---------------------------------------------------------------------------
# read_file / write_file
# ---------------------------------------------------------------------------

class TestReadWriteFile:
    def test_write_and_read(self, workspace):
        workspace.write_file("hello.txt", "world")
        content = workspace.read_file("hello.txt")
        assert content == "world"

    def test_write_creates_parent_dirs(self, workspace):
        workspace.write_file("a/b/c/deep.txt", "deep content")
        content = workspace.read_file("a/b/c/deep.txt")
        assert content == "deep content"

    def test_write_overwrites_existing(self, workspace):
        workspace.write_file("file.txt", "v1")
        workspace.write_file("file.txt", "v2")
        assert workspace.read_file("file.txt") == "v2"

    def test_read_nonexistent_raises(self, workspace):
        with pytest.raises(FileNotFoundError):
            workspace.read_file("does_not_exist.txt")


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------

class TestListFiles:
    def test_list_files_non_recursive(self, workspace):
        workspace.write_file("a.txt", "a")
        workspace.write_file("b.txt", "b")
        workspace.write_file("sub/c.txt", "c")

        files = workspace.list_files(".")
        # Should include top-level files but not files inside sub/
        filenames = [f.replace("\\", "/") for f in files]
        assert "a.txt" in filenames
        assert "b.txt" in filenames
        # README.md is created by init
        assert "README.md" in filenames
        # sub/c.txt should NOT appear in non-recursive listing of "."
        assert "sub/c.txt" not in filenames

    def test_list_files_recursive(self, workspace):
        workspace.write_file("a.txt", "a")
        workspace.write_file("sub/b.txt", "b")
        workspace.write_file("sub/deep/c.txt", "c")

        files = workspace.list_files(".", recursive=True)
        filenames = [f.replace("\\", "/") for f in files]
        assert "a.txt" in filenames
        assert "sub/b.txt" in filenames
        assert "sub/deep/c.txt" in filenames

    def test_list_files_excludes_git_dir(self, workspace):
        files = workspace.list_files(".", recursive=True)
        for f in files:
            assert ".git" not in f.replace("\\", "/").split("/")

    def test_list_files_empty_dir(self, workspace):
        # Create and list a directory with no files
        (workspace.path / "empty_dir").mkdir()
        files = workspace.list_files("empty_dir")
        assert files == []

    def test_list_files_nonexistent_dir(self, workspace):
        files = workspace.list_files("no_such_dir")
        assert files == []


# ---------------------------------------------------------------------------
# search_code
# ---------------------------------------------------------------------------

class TestSearchCode:
    def test_finds_pattern_match(self, workspace):
        workspace.write_file("src/main.c", "int main() {\n    return 0;\n}\n")
        results = workspace.search_code(r"int main")
        assert len(results) >= 1
        match = results[0]
        assert match["content"] == "int main() {"
        assert match["line"] == 1
        assert match["file"].replace("\\", "/") == "src/main.c"

    def test_no_matches_returns_empty(self, workspace):
        workspace.write_file("data.txt", "hello world")
        results = workspace.search_code(r"zzz_not_here")
        assert results == []

    def test_search_with_glob_filter(self, workspace):
        workspace.write_file("code.c", "match_me")
        workspace.write_file("code.py", "match_me")
        results = workspace.search_code(r"match_me", glob="*.c")
        files = [r["file"].replace("\\", "/") for r in results]
        assert "code.c" in files
        assert "code.py" not in files

    def test_multiple_matches_across_files(self, workspace):
        workspace.write_file("a.txt", "hello\nworld")
        workspace.write_file("b.txt", "hello again")
        results = workspace.search_code(r"hello")
        assert len(results) == 2


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------

class TestCommit:
    def test_commit_creates_a_commit(self, workspace):
        workspace.write_file("new.txt", "content")
        sha = workspace.commit("Add new file", files=["new.txt"])
        assert sha is not None
        assert len(sha) == 40  # full hex SHA

    def test_commit_message_in_log(self, workspace):
        workspace.write_file("f.txt", "data")
        workspace.commit("Test commit message", files=["f.txt"])
        last_commit = workspace.repo.head.commit
        assert "Test commit message" in last_commit.message

    def test_commit_all_untracked(self, workspace):
        workspace.write_file("auto1.txt", "a")
        workspace.write_file("auto2.txt", "b")
        sha = workspace.commit("Commit all")
        # Both files should be tracked now
        tracked = [item.path for item in workspace.repo.head.commit.tree.traverse()]
        names = [t.replace("\\", "/") for t in tracked]
        assert "auto1.txt" in names
        assert "auto2.txt" in names

    def test_commit_specific_files(self, workspace):
        workspace.write_file("staged.txt", "yes")
        workspace.write_file("unstaged.txt", "no")
        workspace.commit("Partial commit", files=["staged.txt"])
        # staged.txt should be committed; unstaged.txt should still be untracked
        tracked = [item.path for item in workspace.repo.head.commit.tree.traverse()]
        names = [t.replace("\\", "/") for t in tracked]
        assert "staged.txt" in names
