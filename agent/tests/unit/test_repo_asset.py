"""Carrying a repository as a boot module (intent I2, services/host-repo.md).

The image's probe is `git clone`, so the archive has to be clonable: bare, with
update-server-info applied. And a repository too large for the module budget
must be refused with the number, never truncated into something that looks
like a repository and fails at the first fetch.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from package_image import REPO_ASSET_MAX, RepoTooLarge, _write_repo_asset  # noqa: E402


def _repo(tmp_path: Path, extra_bytes: int = 0) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(src)], check=True)
    (src / "README.md").write_text("hello\n")
    if extra_bytes:
        # Random-ish content so it does not compress away to nothing.
        (src / "big.bin").write_bytes(bytes(range(256)) * (extra_bytes // 256))
    subprocess.run(["git", "-C", str(src), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(src), "-c", "user.email=t@a", "-c", "user.name=t",
                    "commit", "-qm", "first"], check=True)
    return src


def _members(archive: Path) -> set[str]:
    out = subprocess.run(["cpio", "-it"], input=archive.read_bytes(),
                         capture_output=True)
    return set(out.stdout.decode().split())


def test_the_archive_is_clonable_by_construction(tmp_path):
    src = _repo(tmp_path)
    out = tmp_path / "pkg"
    (out / "spec").mkdir(parents=True)
    artifact = _write_repo_asset(src, out, str(src))

    archive = out / "assets" / "repo.cpio"
    assert archive.exists()
    members = _members(archive)
    assert "HEAD" in members
    assert "info/refs" in members, "without it a dumb clone enumerates nothing"
    assert "objects/info/packs" in members, "git update-server-info writes it"
    assert not any(m.startswith(".git/") for m in members), "the archive is a BARE repo"
    assert "README.md" not in members, "a working tree is not served"
    assert artifact.path.endswith("assets/repo.cpio")


def test_the_head_commit_is_recorded(tmp_path):
    src = _repo(tmp_path)
    out = tmp_path / "pkg"
    (out / "spec").mkdir(parents=True)
    head = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    artifact = _write_repo_asset(src, out, str(src))
    assert head[:12] in artifact.implements, "a package must say which commit it carries"


def test_a_repository_over_the_budget_is_refused_with_the_number(tmp_path, monkeypatch):
    """Not truncated: a partial archive looks like a repository and fails at
    the first fetch, which is a worse failure than refusing to build."""
    monkeypatch.setattr("package_image.REPO_ASSET_MAX", 4096)
    src = _repo(tmp_path, extra_bytes=64 * 1024)
    out = tmp_path / "pkg"
    (out / "spec").mkdir(parents=True)
    with pytest.raises(RepoTooLarge, match="module budget"):
        _write_repo_asset(src, out, str(src))
    assert not (out / "assets" / "repo.cpio").exists(), "nothing invalid reaches disk"


def test_something_that_is_not_a_repository_is_refused(tmp_path):
    (tmp_path / "notarepo").mkdir()
    out = tmp_path / "pkg"
    (out / "spec").mkdir(parents=True)
    with pytest.raises(RepoTooLarge, match="not a git repository"):
        _write_repo_asset(tmp_path / "notarepo", out, "x")


def test_the_budget_is_the_module_budget():
    assert REPO_ASSET_MAX == 64 * 1024 * 1024, "boot.md's module-memory budget"
