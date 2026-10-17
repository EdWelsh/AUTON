"""Fetch the domain text in SLM/data/sources.yaml, normalise it, and record what was got.

    python SLM/tools/fetch_domain_text.py                 # every source
    python SLM/tools/fetch_domain_text.py --only man-pages
    python SLM/tools/fetch_domain_text.py --stats-only    # re-count what is cached

Text lands in .cache/slm/domain/<id>/ (gitignored) as one JSONL per source:
{"text", "source", "path", "licence", "commit"}, one record per file, markup
stripped (reStructuredText directives, roff requests). What is committed is
SLM/datasets/domain_text.stats.json: per source the commit fetched, files,
words and distinct words, and how much of it a 1,024-word kernel vocabulary
would cover. That last number is why this text does not train the in-kernel
model directly (SLM/DATA.md).
"""

from __future__ import annotations

import argparse
import collections
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "SLM" / "data" / "sources.yaml"
CACHE = ROOT / ".cache" / "slm" / "domain"
STATS = ROOT / "SLM" / "datasets" / "domain_text.stats.json"


class FetchError(Exception):
    pass


def _git(*args, cwd: Path | None = None, timeout: int = 900) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise FetchError(f"git {' '.join(args)}: {r.stderr.strip()[:300]}")
    return r.stdout


def fetch_git_sparse(src: dict, dest: Path) -> str:
    repo = dest / "repo"
    if not (repo / ".git").exists():
        dest.mkdir(parents=True, exist_ok=True)
        _git("clone", "--depth", "1", "--filter=blob:none", "--sparse", src["repo"], str(repo))
    _git("sparse-checkout", "set", *src["paths"], cwd=repo)
    return _git("rev-parse", "HEAD", cwd=repo).strip()


def strip_markup(text: str, path: str) -> str:
    if re.search(r"\.\d$", path):                          # roff (man pages)
        lines = []
        for line in text.splitlines():
            if line.startswith(('.\\"', "'\\\"")):
                continue
            if line.startswith("."):
                parts = line.split(None, 1)
                if parts[0] in (".TH", ".SH", ".SS", ".B", ".I", ".BR", ".IR", ".RB", ".BI",
                                ".IB", ".RI") and len(parts) > 1:
                    lines.append(parts[1].replace('"', ""))
                continue
            lines.append(line)
        text = "\n".join(lines)
        text = re.sub(r"\\f[BIRP]|\\\(..|\\[-e&]|\\\*\[[^\]]*\]", "", text)
    else:                                                   # reStructuredText
        text = re.sub(r"^\.\. [^\n]*(\n[ \t]+[^\n]*)*", "", text, flags=re.M)
        text = re.sub(r"^[=\-~^\"'`#*+]{3,}\s*$", "", text, flags=re.M)
        text = re.sub(r":\w+:`([^`<]*)(<[^>]*>)?`", r"\1", text)
        text = text.replace("``", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def collect(src: dict, dest: Path, commit: str) -> Path:
    repo = dest / "repo"
    out = dest / f"{src['id']}.jsonl"
    with open(out, "w", encoding="utf-8") as fh:
        for p in src["paths"]:
            for f in sorted((repo / p).rglob("*")):
                if not f.is_file() or not any(fnmatch.fnmatch(f.name, g) for g in src["globs"]):
                    continue
                rel = str(f.relative_to(repo))
                text = strip_markup(f.read_text(encoding="utf-8", errors="replace"), rel)
                if len(text.split()) < 20:
                    continue
                fh.write(json.dumps({"text": text, "source": src["id"], "path": rel,
                                     "licence": src["licence"], "commit": commit}) + "\n")
    return out


def stats(src: dict, path: Path, commit: str, kernel_vocab: int = 1024) -> dict:
    words = collections.Counter()
    files = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        files += 1
        words.update(json.loads(line)["text"].split())
    total = sum(words.values())
    top = sum(n for _, n in words.most_common(kernel_vocab))
    return {"id": src["id"], "title": src["title"], "licence": src["licence"], "use": src["use"],
            "repo": src.get("repo"), "commit": commit, "files": files, "words": total,
            "distinct_words": len(words),
            "kernel_vocab_coverage": round(top / total, 4) if total else 0.0}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only")
    ap.add_argument("--stats-only", action="store_true")
    args = ap.parse_args(argv)
    spec = yaml.safe_load(SOURCES.read_text())
    previous = {s["id"]: s for s in json.loads(STATS.read_text())["sources"]} \
        if STATS.exists() else {}
    for src in spec["sources"]:
        if args.only and src["id"] != args.only:
            continue
        dest = CACHE / src["id"]
        try:
            if args.stats_only:
                commit = _git("rev-parse", "HEAD", cwd=dest / "repo").strip()
            elif src["fetch"] == "git-sparse":
                commit = fetch_git_sparse(src, dest)
            else:
                raise FetchError(f"{src['id']}: fetch {src['fetch']!r} not supported")
            out = collect(src, dest, commit)
            previous[src["id"]] = stats(src, out, commit)
            s = previous[src["id"]]
            print(f"{src['id']}: {s['files']} files, {s['words']:,} words, "
                  f"{s['distinct_words']:,} distinct; a 1,024-word vocabulary covers "
                  f"{100 * s['kernel_vocab_coverage']:.0f}% of tokens  ({out})")
        except (FetchError, subprocess.TimeoutExpired, OSError) as exc:
            print(f"{src['id']}: FAILED {exc}", file=sys.stderr)
    STATS.write_text(json.dumps({"sources": sorted(previous.values(), key=lambda s: s["id"])},
                                indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
