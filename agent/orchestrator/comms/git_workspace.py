"""Git workspace management for agent collaboration.

Agents write through this class, so it is where writing is constrained. Before
this, `write_file` joined a caller-supplied path onto the workspace root and
wrote — which meant an absolute path escaped the workspace entirely, `..`
traversed out of it, and a whole-file write silently discarded whatever was
there. The last of those is on record: an architect overwrote `net.h` with a
placeholder, and that single incident blocked F6, V8 and H7.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import git as _git

# Configure GitPython to find git executable on Windows
_git_exe = shutil.which("git")
if not _git_exe:
    # Common Windows locations
    for candidate in [
        r"C:\Program Files\Git\bin\git.exe",
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Git\bin\git.exe",
    ]:
        if os.path.isfile(candidate):
            _git_exe = candidate
            break
if _git_exe:
    _git.refresh(_git_exe)

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

logger = logging.getLogger(__name__)


class WorkspaceError(Exception):
    """A write the workspace refused. Always names the path and what to do
    instead — an agent that cannot tell why it was refused retries the same
    thing."""


class GitWorkspace:
    """Manages the shared git repository where agents write kernel code.

    Each agent works on a feature branch. The Integrator merges approved
    branches into main. Communication happens through branch state and
    metadata files in .auton/.
    """

    def __init__(self, workspace_path: Path, branch_prefix: str = "agent"):
        self.path = workspace_path.resolve()
        self.branch_prefix = branch_prefix
        self._repo: Repo | None = None
        # Files this workspace has been asked to read. A write over something
        # nobody looked at is how `net.h` became a placeholder — see
        # _resolve_for_write.
        self._seen: set[str] = set()

    def _resolve(self, path: str) -> Path:
        """Resolve a workspace-relative path, or refuse.

        Two things make this necessary rather than defensive. `Path(root) /
        "/tmp/x"` is `/tmp/x` — an absolute path does not join, it *replaces*,
        so the workspace root is silently discarded. And a symlink inside the
        workspace pointing out of it defeats any check made on the string, so
        the resolved result is what gets compared.
        """
        candidate = Path(path)
        if candidate.is_absolute():
            raise WorkspaceError(
                f"refusing an absolute path {path!r}: workspace paths are "
                f"relative to {self.path}, and an absolute one would write "
                f"outside it entirely")

        resolved = (self.path / candidate).resolve()
        try:
            resolved.relative_to(self.path)
        except ValueError:
            raise WorkspaceError(
                f"refusing {path!r}: it resolves to {resolved}, outside the "
                f"workspace at {self.path}") from None
        return resolved

    def _resolve_for_write(self, path: str) -> Path:
        """As above, and refuse to discard a file nobody read.

        Not a size heuristic. "The new content is much shorter" would have
        caught the `net.h` incident and will not catch the next one — the defect
        is writing over something you did not look at, which is exactly what can
        be checked. Creating a new file stays free, because a rule that makes
        every write a read-first ceremony gets worked around.
        """
        resolved = self._resolve(path)
        if resolved.exists() and path not in self._seen:
            raise WorkspaceError(
                f"refusing to overwrite {path!r}, which this workspace has not "
                f"read. Replacing a file sight-unseen is how net.h became a "
                f"placeholder. read_file({path!r}) first, or use edit_file() to "
                f"change part of it")
        return resolved

    @property
    def repo(self) -> Repo:
        if self._repo is None:
            raise RuntimeError("Workspace not initialized. Call init() first.")
        return self._repo

    def init(self) -> None:
        """Initialize or open the workspace git repository."""
        created = False
        try:
            self._repo = Repo(self.path)
            logger.info("Opened existing workspace at %s", self.path)
        except (InvalidGitRepositoryError, NoSuchPathError):
            self.path.mkdir(parents=True, exist_ok=True)
            self._repo = Repo.init(self.path)
            created = True

        # Before any commit, and on both paths. An adopted workspace is as
        # likely to lack an identity as a fresh one, and the seeding commits
        # below are themselves commits — setting this afterwards would leave the
        # very first one relying on whatever the host could derive.
        self._ensure_identity()

        if created:
            # Create initial commit so branches work
            readme = self.path / "README.md"
            readme.write_text("# AUTON Kernel Workspace\n\nGenerated by AUTON agents.\n")
            self._repo.index.add(["README.md"])
            self._repo.index.commit("Initial commit")
            # Create .auton metadata directory
            auton_dir = self.path / ".auton"
            auton_dir.mkdir(exist_ok=True)
            (auton_dir / "tasks").mkdir(exist_ok=True)
            (auton_dir / "messages").mkdir(exist_ok=True)
            self._repo.index.add([".auton"])
            self._repo.index.commit("Add .auton metadata directory")
            logger.info("Initialized new workspace at %s", self.path)

    def _ensure_identity(self) -> None:
        """Give the workspace repo its own committer identity.

        Every commit here is made on an agent's behalf, so the identity is ours
        to state rather than the machine's to supply. Relying on ambient global
        git config meant `git commit` failed with "Committer identity unknown"
        on any host where nobody had set one — a fresh container, a new dev box,
        or the Linux CI runner, which is where this surfaced. macOS hosts here
        happened to have one, so the whole suite passed locally and three tests
        failed in CI.

        Written at repository scope, never --global: this must not reach outside
        the workspace it belongs to.
        """
        with self._repo.config_writer() as cfg:
            cfg.set_value("user", "name", "AUTON agent")
            cfg.set_value("user", "email", "agent@auton.local")

    def create_branch(self, agent_id: str, subsystem: str, component: str) -> str:
        """Create a feature branch for an agent's task.

        Returns the branch name.
        """
        branch_name = f"{self.branch_prefix}/{agent_id}/{subsystem}-{component}"
        if branch_name in [b.name for b in self.repo.branches]:
            logger.info("Branch %s already exists, checking out", branch_name)
            self.repo.git.checkout(branch_name)
        else:
            self.repo.git.checkout("-b", branch_name)
            logger.info("Created branch %s", branch_name)
        return branch_name

    def checkout(self, branch: str) -> None:
        """Switch to a branch."""
        self.repo.git.checkout(branch)

    def checkout_main(self) -> None:
        """Switch back to main branch, keeping work on the branch that made it.

        Untracked files survive `git checkout`. On w12's third live run an
        architect wrote a 255-line header on its design branch without
        committing it; the checkout carried it onto the developer's branch,
        and it was merged as part of a one-line change. Uncommitted work on an
        agent branch is therefore committed there before switching.
        """
        main = self._get_main_branch()
        try:
            current = self.repo.active_branch.name
        except TypeError:           # detached HEAD
            current = None
        if current and current != main:
            if self.commit_pending(current, f"uncommitted work left on {current}"):
                logger.info("Committed uncommitted work on %s before leaving it", current)
        self.repo.git.checkout(main)

    def read_file(self, path: str) -> str:
        """Read a file from the workspace."""
        full_path = self._resolve(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        self._seen.add(path)
        return full_path.read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        """Write a file to the workspace, creating parent directories.

        Whole-file replacement. Kept for creating new files — an agent with no
        way to create one encodes the content somewhere worse — but it refuses
        to overwrite a file this workspace has not read.
        """
        full_path = self._resolve_for_write(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        self._seen.add(path)

    def edit_file(self, path: str, old: str, new: str) -> None:
        """Replace an exact substring that appears exactly once.

        The primitive whose absence caused the incident. An architect replacing
        a header wholesale was a legitimate intent expressed with the wrong
        tool, because the wrong tool was the only one there.

        Exactly once, deliberately: a match count of zero means the agent is
        working from a stale assumption, and more than one means it does not
        know which it is changing. Applied blindly, both are silent corruption.
        """
        full_path = self._resolve(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        content = full_path.read_text(encoding="utf-8")
        count = content.count(old)
        if count == 0:
            raise WorkspaceError(
                f"edit to {path!r} matched nothing. The text to replace is not "
                f"in the file — read it again rather than assuming what it says")
        if count > 1:
            raise WorkspaceError(
                f"edit to {path!r} matched {count} times and must match once. "
                f"Include enough surrounding text to name which one")

        full_path.write_text(content.replace(old, new, 1), encoding="utf-8")
        self._seen.add(path)

    def list_files(self, path: str = ".", recursive: bool = False) -> list[str]:
        """List files in a workspace directory."""
        full_path = self._resolve(path)
        if not full_path.is_dir():
            return []
        if recursive:
            return [
                str(p.relative_to(self.path))
                for p in full_path.rglob("*")
                if p.is_file() and ".git" not in p.parts
            ]
        return [
            str(p.relative_to(self.path))
            for p in full_path.iterdir()
            if p.is_file() and ".git" not in p.parts
        ]

    def search_code(self, pattern: str, glob: str = "*") -> list[dict]:
        """Search workspace files for a pattern."""
        import re

        results = []
        for path in self.path.rglob(glob):
            if not path.is_file() or ".git" in path.parts:
                continue
            try:
                content = path.read_text(encoding="utf-8")
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pattern, line):
                        results.append(
                            {
                                "file": str(path.relative_to(self.path)),
                                "line": i,
                                "content": line.strip(),
                            }
                        )
            except (UnicodeDecodeError, PermissionError):
                continue
        return results

    def commit(self, message: str, files: list[str] | None = None) -> str:
        """Stage and commit changes. Returns the commit hash."""
        if files:
            self.repo.index.add(files)
        else:
            self.repo.git.add("-A")

        if not self.repo.index.diff("HEAD") and not self.repo.untracked_files:
            logger.info("Nothing to commit")
            return self.repo.head.commit.hexsha

        commit = self.repo.index.commit(message)
        logger.info("Committed %s: %s", commit.hexsha[:8], message)
        return commit.hexsha

    # Engine state and build output live inside the workspace but are not work.
    # `git add -A` would commit .auton/state.json onto an agent's branch.
    _NOT_WORK = (":(exclude).auton", ":(exclude)build")

    def has_changes(self, branch: str) -> bool:
        """Whether `branch` carries work: commits ahead of main, or uncommitted
        changes while it is checked out."""
        main = self._get_main_branch()
        if branch == main:
            return False
        if self.repo.git.rev_list("--count", f"{main}..{branch}") != "0":
            return True
        return self._is_current(branch) and bool(
            self.repo.git.status("--porcelain", "--", ".", *self._NOT_WORK))

    def commit_pending(self, branch: str, message: str) -> bool:
        """Commit an agent's uncommitted work on its own branch, excluding
        engine state. Returns whether anything was committed.

        The branch does not have to be checked out. It used to: anything that
        switched the workspace between the agent writing and its result being
        handled — a merge, or a review's compile check — left the work
        uncommitted, and the engine then reported "no output: branch identical
        to main" while a finished implementation sat in the working tree. That
        happened to a 364-line TFTP server (w14, qwen3.5:27b).

        Git carries uncommitted changes across a checkout when they do not
        conflict, which is the normal case here: agent branches descend from
        main and the work is usually new files. When it does conflict git
        refuses, and so does this — saying so beats committing the work
        somewhere it does not belong.
        """
        if not self._is_current(branch):
            try:
                self.repo.git.checkout(branch)
            except GitCommandError as exc:
                logger.warning("cannot carry pending work to %s: %s", branch, exc)
                return False
        self.repo.git.add("-A", "--", ".", *self._NOT_WORK)
        if not self.repo.git.diff("--cached", "--name-only"):
            return False
        self.repo.index.commit(message)
        return True

    def _is_current(self, branch: str) -> bool:
        try:
            return self.repo.active_branch.name == branch
        except TypeError:          # detached HEAD
            return False

    def branch_diff(self, branch: str) -> tuple[str, list[str]]:
        """The change `branch` makes against main: (unified diff, changed paths).
        Three-dot, so it is what the branch added, whatever is checked out."""
        main = self._get_main_branch()
        text = self.repo.git.diff(f"{main}...{branch}", "--", ".", *self._NOT_WORK)
        names = self.repo.git.diff("--name-only", f"{main}...{branch}", "--", ".",
                                   *self._NOT_WORK).split()
        return text, names

    def diff(self, branch: str | None = None) -> str:
        """Get diff of current changes or against a branch."""
        if branch:
            return self.repo.git.diff(branch)
        return self.repo.git.diff()

    def get_branch_status(self) -> dict[str, dict]:
        """Get the status of all agent branches."""
        main = self._get_main_branch()
        status = {}
        for branch in self.repo.branches:
            if branch.name == main:
                continue
            ahead = len(
                list(self.repo.iter_commits(f"{main}..{branch.name}"))
            )
            status[branch.name] = {
                "ahead": ahead,
                "last_commit": branch.commit.message.strip(),
                "last_author": str(branch.commit.author),
                "last_date": branch.commit.committed_datetime.isoformat(),
            }
        return status

    def merge_branch(self, branch: str) -> bool:
        """Merge a branch into main. Returns True if successful."""
        main = self._get_main_branch()
        self.repo.git.checkout(main)
        try:
            self.repo.git.merge(branch, "--no-ff", "-m", f"Merge {branch}")
            logger.info("Merged %s into %s", branch, main)
            return True
        except GitCommandError as e:
            logger.error("Merge conflict merging %s: %s", branch, e)
            self.repo.git.merge("--abort")
            return False

    def _get_main_branch(self) -> str:
        """Get the name of the main branch."""
        for name in ("main", "master"):
            if name in [b.name for b in self.repo.branches]:
                return name
        return "main"
