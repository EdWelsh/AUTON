"""Errata lineage (hardware-truth H9): the same defect, carried across generations.

    python agent/tools/lineage.py --config agent/hardware/lineage.yaml --out lineage.json

Intel carries errata from one generation's specification update to the next,
often word for word, under a new id. Two errata in different documents are
linked when their normalised titles and their detail text are similar enough
(`score()` >= LINK_THRESHOLD); linked errata form a chain, and every member of
a chain is cited (document, id, page).

LINK_THRESHOLD is a starting value. A person confirms it against a sample of
real pairs before a chain is quoted (the plan's Task 2); `--pairs` prints the
borderline pairs to review.

One document is not a lineage: with fewer than two documents this refuses.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "agent" / "hardware" / "lineage.yaml"
CLASSES = ROOT / "agent" / "hardware" / "erratum-classes.yaml"

LINK_THRESHOLD = 0.6
TITLE_WEIGHT = 0.6
DETAIL_WEIGHT = 0.4
# Words that carry no identity: hedges every erratum title uses.
STOP = {"may", "might", "can", "could", "be", "not", "the", "a", "an", "of", "on", "in", "to",
        "for", "when", "with", "is", "are", "and", "or", "if", "by", "at", "as", "from"}


class LineageError(Exception):
    pass


@dataclass(frozen=True)
class Erratum:
    document: str        # "intel/intel-spec-update-12"
    generation: int      # ordering key: the generation the document covers
    key: str             # the document's own id, e.g. ADL038
    title: str
    detail: str = ""
    status: str = ""
    page: int | None = None

    def cite(self) -> dict:
        return {"document": self.document, "generation": self.generation, "id": self.key,
                "title": self.title, "page": self.page}


@dataclass
class Chain:
    members: list[Erratum] = field(default_factory=list)

    @property
    def generations(self) -> list[int]:
        return sorted({m.generation for m in self.members})


def tokens(text: str) -> set[str]:
    t = text.lower().replace("®", " ").replace("™", " ")
    t = re.sub(r"[^a-z0-9#_\-\. ]+", " ", t)
    return {w.strip(".-") for w in t.split() if w.strip(".-") and w not in STOP}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def score(a: Erratum, b: Erratum) -> float:
    s = TITLE_WEIGHT * jaccard(tokens(a.title), tokens(b.title))
    if a.detail and b.detail:
        s += DETAIL_WEIGHT * jaccard(tokens(a.detail), tokens(b.detail))
    else:
        s /= TITLE_WEIGHT          # title alone decides when a detail is missing
    return s


def link(docs: dict[str, list[Erratum]], threshold: float = LINK_THRESHOLD) -> list[Chain]:
    """Chains across documents: each erratum links to its best match in every
    other document, when that match clears the threshold. Union-find."""
    if len(docs) < 2:
        raise LineageError(f"{len(docs)} document(s): one document is not a lineage")
    everyone = [e for es in docs.values() for e in es]
    parent = {e: e for e in everyone}

    def find(x: Erratum) -> Erratum:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    names = sorted(docs)
    for i, da in enumerate(names):
        for db in names[i + 1:]:
            for a in docs[da]:
                best = max(docs[db], key=lambda b: score(a, b), default=None)
                if best is not None and score(a, best) >= threshold:
                    parent[find(a)] = find(best)
    groups: dict[Erratum, list[Erratum]] = {}
    for e in everyone:
        groups.setdefault(find(e), []).append(e)
    return [Chain(sorted(g, key=lambda e: (e.generation, e.key))) for g in groups.values()]


def load_classes(path: Path = CLASSES) -> dict:
    return yaml.safe_load(path.read_text())


def classify(e: Erratum, classes: dict) -> str:
    override = (classes.get("overrides") or {}).get(f"{e.document}/{e.key}")
    if override:
        return override
    for text in (e.title, e.detail):
        low = f" {text.lower()} "
        for c in classes["classes"]:
            if any(k in low for k in c["keywords"]):
                return c["name"]
    return classes.get("default", "other")


def load_documents(config: Path = CONFIG) -> dict[str, list[Erratum]]:
    """Every document the config lists that has been ingested."""
    from vendor_ingest import IngestError, ingest

    cfg = yaml.safe_load(config.read_text())
    out: dict[str, list[Erratum]] = {}
    for d in cfg["documents"]:
        try:
            records, _ = ingest(d["vendor"], d["id"])
        except IngestError as exc:
            print(f"  {d['vendor']}/{d['id']}: not ingested ({exc})", file=sys.stderr)
            continue
        name = f"{d['vendor']}/{d['id']}"
        out[name] = [Erratum(name, int(d["generation"]), r.key, r.title, r.detail or "",
                             r.status or "", r.page) for r in records if r.kind == "erratum"]
    return out


def report(chains: list[Chain], classes: dict) -> dict:
    recurring = [c for c in chains if len(c.generations) > 1]
    return {
        "threshold": LINK_THRESHOLD,
        "chains": len(chains),
        "recurring": len(recurring),
        "lineages": [{"class": classify(c.members[0], classes), "generations": c.generations,
                      "members": [m.cite() for m in c.members]}
                     for c in sorted(recurring, key=lambda c: -len(c.generations))],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--config", type=Path, default=CONFIG)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    docs = load_documents(args.config)
    try:
        chains = link(docs)
    except LineageError as exc:
        print(f"lineage: {exc}. Ingest more of the documents {args.config.name} lists "
              f"(vendor_fetch.py --from-file).", file=sys.stderr)
        return 2
    rep = report(chains, load_classes())
    print(f"{len(docs)} documents, {rep['chains']} chains, {rep['recurring']} recurring")
    if args.out:
        args.out.write_text(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
