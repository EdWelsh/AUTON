"""Can lineage retrodict? (hardware-truth H9, the PRD's Open Question 5)

    python agent/tools/retrodict.py --cutoff 12

Hide every document from generation `cutoff` on. From the earlier ones alone,
predict (1) which erratum classes the cutoff generation will have, and (2)
which of the latest earlier generation's unfixed errata it will carry over.
Then score both against what the cutoff generation actually published.

Each score sits beside a baseline that uses no lineage at all, because a
prediction is only worth quoting if it beats guessing: for classes, "every
class seen before recurs"; for carry-over, "every erratum of the last
generation recurs". The result is published whichever way it falls.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lineage import (CONFIG, LINK_THRESHOLD, Erratum, LineageError, classify,  # noqa: E402
                     load_classes, load_documents, score)

# A class is predicted when it appeared in at least RECUR_MIN of the last
# RECUR_WINDOW earlier generations.
RECUR_WINDOW = 3
RECUR_MIN = 2


@dataclass(frozen=True)
class Score:
    predicted: int
    actual: int
    hit: int

    @property
    def precision(self) -> float:
        return self.hit / self.predicted if self.predicted else 0.0

    @property
    def recall(self) -> float:
        return self.hit / self.actual if self.actual else 0.0

    def row(self, label: str) -> str:
        return (f"  {label:<34} predicted {self.predicted:>3}  actual {self.actual:>3}  "
                f"hit {self.hit:>3}  precision {self.precision:.2f}  recall {self.recall:.2f}")


def _split(docs: dict[str, list[Erratum]], cutoff: int):
    by_gen: dict[int, list[Erratum]] = {}
    for es in docs.values():
        for e in es:
            by_gen.setdefault(e.generation, []).append(e)
    prior = sorted(g for g in by_gen if g < cutoff)
    if cutoff not in by_gen:
        raise LineageError(f"generation {cutoff} is not ingested: nothing to score against")
    if len(prior) < 2:
        raise LineageError(f"{len(prior)} earlier generation(s) before {cutoff}: "
                           f"one document is not a lineage")
    return by_gen, prior


def classes_score(docs: dict[str, list[Erratum]], cutoff: int, classes: dict) -> tuple[Score, Score]:
    by_gen, prior = _split(docs, cutoff)
    seen = {g: {classify(e, classes) for e in by_gen[g]} for g in prior}
    window = prior[-RECUR_WINDOW:]
    counts: dict[str, int] = {}
    for g in window:
        for c in seen[g]:
            counts[c] = counts.get(c, 0) + 1
    predicted = {c for c, n in counts.items() if n >= min(RECUR_MIN, len(window))}
    baseline = set().union(*seen.values())
    actual = {classify(e, classes) for e in by_gen[cutoff]}
    return (Score(len(predicted), len(actual), len(predicted & actual)),
            Score(len(baseline), len(actual), len(baseline & actual)))


def carry_score(docs: dict[str, list[Erratum]], cutoff: int,
                threshold: float = LINK_THRESHOLD) -> tuple[Score, Score]:
    """Which of the latest earlier generation's errata recur in the cutoff one.

    Actual: those that link (score >= threshold) to an erratum of the cutoff
    generation. Lineage predicts the unfixed ones recur; the baseline predicts
    all of them (recall 1 by construction, so only its precision says anything).
    """
    by_gen, prior = _split(docs, cutoff)
    last, target = by_gen[prior[-1]], by_gen[cutoff]
    actual = {e for e in last if any(score(e, t) >= threshold for t in target)}
    predicted = {e for e in last if e.status.strip().lower() != "fixed"}
    return (Score(len(predicted), len(actual), len(predicted & actual)),
            Score(len(last), len(actual), len(actual)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--cutoff", type=int, required=True, help="generation to hide and predict")
    ap.add_argument("--config", type=Path, default=CONFIG)
    args = ap.parse_args(argv)
    docs = load_documents(args.config)
    try:
        cls, cls_base = classes_score(docs, args.cutoff, load_classes())
        car, car_base = carry_score(docs, args.cutoff)
    except LineageError as exc:
        print(f"retrodict: {exc}", file=sys.stderr)
        return 2
    earlier = sorted({e.generation for es in docs.values() for e in es if e.generation < args.cutoff})
    print(f"retrodiction of generation {args.cutoff} from generations {earlier}")
    print(cls.row("classes, lineage"))
    print(cls_base.row("classes, baseline (all seen)"))
    print(car.row("carry-over, lineage (unfixed)"))
    print(car_base.row("carry-over, baseline (all)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
