"""A content hash of a directory tree, for the staged subject (A2).

The subject application is evidence, and evidence the analysis can edit is not
evidence. The hash is taken when the subject is staged and checked again before
anything built on it is accepted, so a change by any route — a file tool, a
`python -c` through the shell tool, a `git checkout` — is detected.

What is hashed, per entry, sorted by path:

- a regular file: its path, whether it is executable, and a sha256 of its bytes;
- a symlink: its path and the link *text*. Never followed: a link pointing out
  of the tree must not make the hash depend on (or read) what it points at.

Write bits are deliberately not hashed. Staging removes them, and a hash that
changed when the subject was made read-only would fail its own first check.
Empty directories are not hashed; they carry nothing an application reads.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path


def manifest(root: Path) -> dict[str, str]:
    """Relative POSIX path -> a digest of that entry."""
    root = Path(root)
    entries: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # History is not the subject: staging exports without .git, so a hash
        # of the source must not include it either (w22 whoami).
        dirnames[:] = [d for d in dirnames if d != ".git"]
        base = Path(dirpath)
        # os.walk lists a symlink to a directory under dirnames; hash it as a
        # link and do not descend (followlinks=False already stops descent).
        for name in sorted(dirnames + filenames):
            full = base / name
            rel = full.relative_to(root).as_posix()
            st = full.lstat()
            if stat.S_ISLNK(st.st_mode):
                entries[rel] = "link:" + os.readlink(full)
            elif stat.S_ISREG(st.st_mode):
                exe = "x" if st.st_mode & stat.S_IXUSR else "-"
                entries[rel] = f"file:{exe}:{_file_digest(full)}"
    return entries


def digest(entries: dict[str, str]) -> str:
    h = hashlib.sha256()
    for rel in sorted(entries):
        h.update(rel.encode("utf-8", "surrogateescape"))
        h.update(b"\0")
        h.update(entries[rel].encode("utf-8", "surrogateescape"))
        h.update(b"\n")
    return h.hexdigest()


def tree_hash(root: Path) -> str:
    return digest(manifest(root))


def differences(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """What changed between two manifests, as readable lines."""
    out = []
    for rel in sorted(set(before) | set(after)):
        if rel not in after:
            out.append(f"removed {rel}")
        elif rel not in before:
            out.append(f"added {rel}")
        elif before[rel] != after[rel]:
            out.append(f"changed {rel}")
    return out


def _file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()
