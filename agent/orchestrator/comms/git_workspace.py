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
import re
import shutil
from pathlib import Path

import git as _git

from orchestrator.comms import subject_hash

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


# Where a subject application is staged for analysis (application-to-
# environment A2). Nothing may write under it: the subject is evidence.
SUBJECT_DIR = ".auton/subject"


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
        self._subject_manifest: dict[str, str] | None = None
        self.subject_commit: str | None = None

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
        self._refuse_subject(path, resolved)
        if resolved.exists() and path not in self._seen:
            raise WorkspaceError(
                f"refusing to overwrite {path!r}, which this workspace has not "
                f"read. Replacing a file sight-unseen is how net.h became a "
                f"placeholder. read_file({path!r}) first, or use edit_file() to "
                f"change part of it")
        return resolved

    # --- the staged subject (A2) ------------------------------------------ #

    @property
    def subject_path(self) -> Path:
        return self.path / SUBJECT_DIR

    def _refuse_subject(self, path: str, resolved: Path) -> None:
        """Refuse an agent's write under `.auton/`: the staged subject, and
        everything else the engine keeps there — the manifest the package gate
        is handed, state, reports (w18 review H1: a Packager could otherwise
        empty the requirements its own image is checked against).

        Compared by file identity, not by string: on a case-insensitive
        filesystem `.AUTON/subject/app.py` is the same file, and a prefix check
        on the text would let it through.
        """
        subject, engine = self.subject_path, self.path / ".auton"
        for candidate in (resolved, *resolved.parents):
            if candidate == self.path or self.path not in (candidate, *candidate.parents):
                break
            if not candidate.exists():
                continue
            if subject.exists() and os.path.samefile(candidate, subject):
                raise WorkspaceError(
                    f"refusing to write {path!r}: {SUBJECT_DIR}/ is the application "
                    f"under analysis, and evidence the analysis can edit is not "
                    f"evidence. Write findings under analysis/ instead")
            if engine.exists() and os.path.samefile(candidate, engine):
                raise WorkspaceError(
                    f"refusing to write {path!r}: .auton/ is the engine's — its state, "
                    f"and the manifest your work is checked against. Agents do not "
                    f"write there")

    def stage_subject(self, source: Path) -> str:
        """Stage an application read-only at SUBJECT_DIR; return its tree hash.

        A git repository is exported at HEAD (`git archive`), so the history
        and any uncommitted edits are not part of what is analysed, and the
        commit is recorded. Anything else is copied with symlinks kept as
        links. Write bits are then removed. The hash is what `verify_subject`
        checks later, and what an artifact record's `subject.tree_hash` cites.
        """
        source = Path(source).resolve()
        dest = self.subject_path
        if dest.exists():
            raise WorkspaceError(
                f"a subject is already staged at {SUBJECT_DIR}/; restaging would "
                f"replace evidence mid-analysis. Unstage it, or start a new run")
        if not source.is_dir():
            raise WorkspaceError(f"no application directory at {source}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._exclude_from_git(SUBJECT_DIR)
        try:
            self._copy_subject(source, dest)
        except Exception as exc:
            # A half-staged subject is writable and unhashed; left behind, the
            # retry would be refused as "already staged" (w17 review).
            self.unstage_subject()
            raise WorkspaceError(f"could not stage {source}: {exc}") from exc

        self._subject_manifest = subject_hash.manifest(dest)
        _make_read_only(dest)
        digest = subject_hash.digest(self._subject_manifest)
        logger.info("Staged subject %s at %s (tree %s)", source, SUBJECT_DIR, digest[:12])
        return digest

    def _copy_subject(self, source: Path, dest: Path) -> None:
        if (source / ".git").exists():
            import io
            import subprocess
            import tarfile
            head = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                                  check=True, capture_output=True, text=True).stdout.strip()
            archive = subprocess.run(["git", "-C", str(source), "archive", "--format=tar", head],
                                     check=True, capture_output=True).stdout
            dest.mkdir()
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(dest, filter="data")
            self.subject_commit = head
        else:
            shutil.copytree(source, dest, symlinks=True,
                            ignore=shutil.ignore_patterns(".git"))
            self.subject_commit = None

    def verify_subject(self, expected: str) -> None:
        """Refuse if the staged subject differs from the tree hashed at staging,
        naming what changed. Whatever wrote it — a file tool, the shell, git —
        a changed subject means nothing built on it can be trusted."""
        root = self.subject_path
        if not root.exists():
            raise WorkspaceError(f"no subject staged at {SUBJECT_DIR}/")
        now = subject_hash.manifest(root)
        if subject_hash.digest(now) == expected:
            return
        changed = (subject_hash.differences(self._subject_manifest, now)
                   if self._subject_manifest is not None else [])
        raise WorkspaceError(
            f"the staged subject changed after it was hashed "
            f"({', '.join(changed[:10]) or 'tree hash differs'}); evidence the "
            f"analysis can edit is not evidence, so this record is refused")

    def unstage_subject(self) -> None:
        """Remove the staged subject, restoring write bits so it can be removed."""
        root = self.subject_path
        if not root.exists() and not root.is_symlink():
            return
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            os.chmod(dirpath, 0o755)
            for name in filenames:
                full = os.path.join(dirpath, name)
                if not os.path.islink(full):
                    os.chmod(full, 0o644)
        shutil.rmtree(root)
        self._subject_manifest = None
        self.subject_commit = None

    def _exclude_from_git(self, rel: str) -> None:
        """Keep `rel` out of every `git add -A`, including an agent's own via
        the shell tool, by listing it in the workspace's local exclude file."""
        # Asked of git, not assumed: in a worktree `.git` is a file, and the
        # exclude file lives in the common git directory (w17 review).
        exclude = Path(self.repo.git.rev_parse("--git-path", "info/exclude"))
        if not exclude.is_absolute():
            exclude = self.path / exclude
        exclude.parent.mkdir(parents=True, exist_ok=True)
        lines = exclude.read_text().splitlines() if exclude.exists() else []
        entry = f"/{rel}/"
        if entry not in lines:
            exclude.write_text("\n".join([*lines, entry]) + "\n")

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
        self._exclude_engine_state()

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

    def _exclude_engine_state(self) -> None:
        """Keep `.auton/` and `build/` out of any `git add -A`, at repository scope."""
        exclude = Path(self._repo.git_dir) / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        have = exclude.read_text().splitlines() if exclude.exists() else []
        want = [e for e in (".auton/", "build/") if e not in have]
        if want:
            exclude.write_text("\n".join([*have, *want]) + "\n")

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

    def branch_exists(self, branch: str) -> bool:
        return branch in [b.name for b in self.repo.branches]

    def main_head(self) -> str:
        """The commit main points at."""
        return self.repo.git.rev_parse(self._get_main_branch())

    def current_branch(self) -> str | None:
        try:
            return self.repo.active_branch.name
        except TypeError:           # detached HEAD
            return None

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
        self._checkout_discarding_engine_state(main)

    def _checkout_discarding_engine_state(self, branch: str) -> None:
        """`git checkout`, tolerating tracked engine state (`.auton/...`).

        Task metadata is rewritten on whatever branch is checked out; if an earlier commit
        tracked it, the next checkout is refused as "local changes would be overwritten"
        (R6, R10, R11 and R12 died on `.auton/tasks/<id>.json`, w23). The files are the
        engine's own record, kept in state.json; the checkout's version is restored and
        the switch retried. Changes to anything else still make the checkout fail loudly.
        """
        try:
            self.repo.git.checkout(branch)
        except GitCommandError as exc:
            blocking = [p for p in re.findall(r"^\s+(\S+)$", str(exc.stderr or exc), re.M)
                        if p.startswith(".auton/")]
            debris = untracked_blockers(str(exc.stderr or exc))
            if not blocking and not debris:
                raise
            if blocking:
                self.repo.git.checkout("--", *blocking)
            for rel in debris:      # a log or object file a gate left behind, not work
                target = Path(self.repo.working_tree_dir) / rel
                if target.is_file():
                    target.unlink()
            logger.warning("Cleared %d engine-state file(s) and %d untracked file(s) to switch to %s",
                           len(blocking), len(debris), branch)
            self.repo.git.checkout(branch)

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
        self._refuse_subject(path, full_path)
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
            if path.is_symlink():
                # A link is read through only when it stays inside the
                # workspace; one pointing out would leak the file it names.
                try:
                    path.resolve().relative_to(self.path)
                except ValueError:
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
            # index.add ignores .gitignore and info/exclude, so a subject path
            # named explicitly would be committed; it is evidence, not work.
            kept = [f for f in files if not _under(f, SUBJECT_DIR)]
            if len(kept) != len(files):
                logger.warning("Not committing files under %s/: the subject is not work",
                               SUBJECT_DIR)
                if not kept:
                    return self.repo.head.commit.hexsha
            self.repo.index.add(kept)
        else:
            self._stage_work()

        if not self.repo.index.diff("HEAD") and not self.repo.untracked_files:
            logger.info("Nothing to commit")
            return self.repo.head.commit.hexsha

        commit = self.repo.index.commit(message)
        logger.info("Committed %s: %s", commit.hexsha[:8], message)
        return commit.hexsha

    # Engine state and build output live inside the workspace but are not work.
    # `git add -A` would commit .auton/state.json onto an agent's branch.
    _NOT_WORK = (":(exclude).auton", ":(exclude)build")

    def _stage_work(self) -> None:
        """Stage every change that is work, and nothing that is engine state.

        `git add -A -- . :(exclude)build` exits 1 ("paths are ignored") when `build` is in
        .gitignore, as the kernel base's is: R3 died on its first commit (w23). So engine
        state is excluded by pathspec only for `.auton`, and `build` is unstaged afterwards,
        which git accepts whether or not it is ignored.
        """
        self.repo.git.add("-A", "--", ".")     # .auton/ and build/ are in info/exclude
        self.repo.git.rm("-r", "--cached", "-q", "--ignore-unmatch", "--", "build", ".auton")

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
        self._stage_work()
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
        """Merge a branch into main. Returns True if successful.

        A merge can also be refused before it starts: untracked files in main's working
        tree that the branch would add (a build log an earlier task left behind). That
        is not a conflict, there is no merge to abort (w23: R10's orchestrator died on
        `git merge --abort`), and the files are the orchestrator's own debris, so they
        are removed and the merge retried once.
        """
        main = self._get_main_branch()
        self._checkout_discarding_engine_state(main)
        for attempt in (1, 2):
            try:
                self.repo.git.merge(branch, "--no-ff", "-m", f"Merge {branch}")
                logger.info("Merged %s into %s", branch, main)
                return True
            except GitCommandError as e:
                blocking = untracked_blockers(str(e))
                if blocking and attempt == 1:
                    for rel in blocking:
                        target = Path(self.repo.working_tree_dir) / rel
                        if target.is_file():
                            target.unlink()
                    logger.warning("Removed %d untracked file(s) blocking the merge of %s",
                                   len(blocking), branch)
                    continue
                logger.error("Merge conflict merging %s: %s", branch, e)
                try:
                    self.repo.git.merge("--abort")
                except GitCommandError:
                    pass        # refused before it began: nothing to abort
                return False
        return False

    def _get_main_branch(self) -> str:
        """Get the name of the main branch."""
        for name in ("main", "master"):
            if name in [b.name for b in self.repo.branches]:
                return name
        return "main"


def untracked_blockers(stderr: str) -> list[str]:
    """Paths git names as untracked files a merge would overwrite. Pure."""
    m = re.search(r"untracked working tree files would be overwritten by (?:merge|checkout):\s*\n((?:\s+\S.*\n)+)",
                  stderr)
    return [ln.strip() for ln in m.group(1).splitlines() if ln.strip()] if m else []


def _make_read_only(root: Path) -> None:
    """Remove every write bit under `root`, files first and directories last,
    keeping execute bits. Links are left alone: chmod would follow them."""
    for dirpath, dirnames, filenames in os.walk(root, topdown=False, followlinks=False):
        for name in filenames:
            full = os.path.join(dirpath, name)
            if not os.path.islink(full):
                os.chmod(full, os.stat(full).st_mode & ~0o222)
        os.chmod(dirpath, os.stat(dirpath).st_mode & ~0o222)


def _under(path: str, directory: str) -> bool:
    """Whether workspace-relative `path` is `directory` or inside it."""
    norm = os.path.normpath(path).replace(os.sep, "/")
    return norm == directory or norm.startswith(directory + "/")
