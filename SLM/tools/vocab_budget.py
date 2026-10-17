"""Can this corpus train the model the kernel actually runs?

The in-kernel tokenizer is word-level (kernel/slm/neural/neural_backend.c:
slm_neural_tokenize): it splits on spaces, matches each word exactly and
case-sensitively against the vocabulary, and scans the whole vocabulary per
word. So the vocabulary is a hard budget (chat_tiny and chat_small: 1024), and
every word outside it becomes <unk>, at training time and at the prompt.

A corpus can look large and still be useless here: the hardware reference
corpus has 13,718 distinct words, and the 15% of its tokens a 1024-word
vocabulary drops are precisely the ids and names that carry its facts. This
measures that before anyone spends a training run on it.

Reported per corpus, with the vocabulary built the way tokenizer.py builds it
(frequency-ranked, special tokens first):

    answer_unk   share of ANSWER tokens that would be <unk>: the model cannot say them
    prompt_unk   share of question tokens that would be <unk>: the model cannot read them
    lost_facts   rows whose answer contains at least one <unk> token

    python SLM/tools/vocab_budget.py SLM/datasets/os_chat.jsonl --vocab 1024
    python SLM/tools/vocab_budget.py SLM/datasets/*.jsonl --vocab 1024 --max-answer-unk 0.01

Exit 1 when a corpus exceeds --max-answer-unk: it does not fit the kernel's model.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tokenizer import SPECIAL_TOKENS  # noqa: E402

KERNEL_VOCAB = 1024        # SLM/configs/chat_tiny.yaml and chat_small.yaml


def rows(paths: list[Path]):
    for p in paths:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                yield r.get("text", ""), r.get("response") or r.get("next_action") or ""


def measure(paths: list[Path], vocab: int = KERNEL_VOCAB) -> dict:
    data = list(rows(paths))
    counts = collections.Counter()
    for q, a in data:
        counts.update(q.split())
        counts.update(a.split())
    keep = {w for w, _ in counts.most_common(max(vocab - len(SPECIAL_TOKENS), 0))}
    a_tok = a_unk = q_tok = q_unk = lost = 0
    for q, a in data:
        qs, as_ = q.split(), a.split()
        q_tok += len(qs)
        q_unk += sum(w not in keep for w in qs)
        miss = sum(w not in keep for w in as_)
        a_tok += len(as_)
        a_unk += miss
        lost += miss > 0
    return {"corpora": [str(p) for p in paths], "rows": len(data), "distinct_words": len(counts),
            "vocab": vocab, "fits": len(counts) + len(SPECIAL_TOKENS) <= vocab,
            "answer_unk": a_unk / a_tok if a_tok else 0.0,
            "prompt_unk": q_unk / q_tok if q_tok else 0.0,
            "lost_facts": lost, "tokens": a_tok + q_tok}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("datasets", nargs="+")
    ap.add_argument("--vocab", type=int, default=KERNEL_VOCAB)
    ap.add_argument("--max-answer-unk", type=float, default=0.0)
    ap.add_argument("--together", action="store_true",
                    help="measure the corpora as one training set (one shared vocabulary)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    groups = [[Path(d) for d in args.datasets]] if args.together else \
        [[Path(d)] for d in args.datasets]
    worst = 0.0
    for g in groups:
        m = measure(g, args.vocab)
        worst = max(worst, m["answer_unk"])
        if args.json:
            print(json.dumps(m))
            continue
        verdict = "FITS" if m["answer_unk"] <= args.max_answer_unk else "DOES NOT FIT"
        print(f"{verdict:13} {' + '.join(Path(c).name for c in m['corpora'])}: {m['rows']} rows, "
              f"{m['distinct_words']} words vs vocab {m['vocab']}; answer <unk> "
              f"{100 * m['answer_unk']:.1f}%, prompt <unk> {100 * m['prompt_unk']:.1f}%, "
              f"{m['lost_facts']} answers lose a word")
    return 0 if worst <= args.max_answer_unk else 1


if __name__ == "__main__":
    raise SystemExit(main())
