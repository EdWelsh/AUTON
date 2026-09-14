"""Split an eval run by whether each prompt is in scope for an image.

A scoped model is *supposed* to decline a kubernetes question. Scoring it
against the full 65-prompt set as one number would count that correct refusal
as a failure and hide the result the scoping experiment exists to produce.

So: classify every prompt by the capabilities it depends on, then score the
in-scope and out-of-scope halves separately.

    python SLM/tools/eval_scope.py --manifest SLM/manifests/doom.json \
        --results tests/eval/scoped-doom.json

With no --results it just prints the split, which is worth seeing before a
training run rather than after.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SLM" / "tools"))

from build_corpus import Manifest, capabilities_mentioned  # noqa: E402

# Verdicts that mean the model did its job. `honest_roadmap` is a success: an
# OS that says "I cannot do that yet, here is why" is behaving correctly.
GOOD = {"correct", "honest_roadmap"}


def prompt_capabilities(prompt: dict) -> set[str]:
    """What an answer to this prompt would have to depend on.

    Read from the prompt text plus its expected answer where one exists — the
    expectation is the better signal, since "what is my ip" only reveals itself
    as a network question through the answer.
    """
    text = prompt["prompt"] + " " + (prompt.get("expect") or "")
    return capabilities_mentioned(text)


def classify(prompts: list[dict], manifest: Manifest) -> dict[str, list[dict]]:
    in_scope, out_of_scope = [], []
    for p in prompts:
        caps = prompt_capabilities(p)
        (in_scope if manifest.admits(caps) else out_of_scope).append(
            {**p, "caps": sorted(caps)}
        )
    return {"in_scope": in_scope, "out_of_scope": out_of_scope}


def _score(rows: list[dict]) -> tuple[int, int, float]:
    good = sum(1 for r in rows if r.get("verdict") in GOOD)
    total = len(rows)
    return good, total, (100.0 * good / total if total else 0.0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--prompts", default=str(ROOT / "tests" / "eval" / "prompts.jsonl"))
    ap.add_argument("--results", default=None,
                    help="eval.sh --json output; scores each half when given")
    ap.add_argument("--subset", default=None,
                    help="only ids listed in this file (one per line), to compare "
                         "against a baseline scored on a smaller set")
    args = ap.parse_args(argv)

    manifest = Manifest.load(args.manifest)
    prompts = [json.loads(l) for l in Path(args.prompts).read_text().splitlines() if l.strip()]

    if args.subset:
        keep = {l.strip() for l in Path(args.subset).read_text().splitlines() if l.strip()}
        prompts = [p for p in prompts if p["id"] in keep]

    split = classify(prompts, manifest)
    print(f"manifest: {args.manifest}"
          + (f" — {manifest.intent!r}" if manifest.intent else ""))
    print(f"excludes: {', '.join(sorted(manifest.excludes)) or 'none'}")
    print(f"  in scope     {len(split['in_scope']):3d}")
    print(f"  out of scope {len(split['out_of_scope']):3d}")

    if not args.results:
        for p in split["out_of_scope"]:
            print(f"    OUT {p['id']:10s} {p['prompt'][:50]:50s} {p['caps']}")
        return 0

    data = json.loads(Path(args.results).read_text())
    by_id = {r["id"]: r for r in data["results"]}
    missing = [p["id"] for p in prompts if p["id"] not in by_id]
    if missing:
        print(f"WARNING: {len(missing)} prompts absent from results: {missing[:5]}")

    print()
    for half in ("in_scope", "out_of_scope"):
        rows = [by_id[p["id"]] for p in split[half] if p["id"] in by_id]
        good, total, pct = _score(rows)
        garbage = total - good
        label = "IN SCOPE" if half == "in_scope" else "OUT OF SCOPE"
        print(f"{label:14s} {good:2d}/{total:2d} correct-or-honest ({pct:.0f}%), "
              f"{garbage} garbage ({100 - pct:.0f}%)")
        for r in rows:
            if r.get("verdict") not in GOOD:
                print(f"    GARBAGE {r['id']:10s} {r['prompt'][:40]:40s} "
                      f"-> {str(r.get('answer'))[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
