"""Word-level tokenizer trainer/encoder.

A dependency-free, deterministic tokenizer: it builds a frequency-ranked
vocabulary (plus special tokens) and encodes text to integer IDs. This keeps the
data pipeline runnable without heavyweight tokenizer libraries; the neural
backend can swap in a BPE vocab of the same JSON shape later.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# <sep> divides a question from its answer in the training stream. Appended
# last so <pad>=0, <unk>=1, <bos>=2, <eos>=3 keep their ids — the kernel and the
# parity harness both rely on 0 and 3.
SPECIAL_TOKENS = ["<pad>", "<unk>", "<bos>", "<eos>", "<sep>"]


def _read_pairs(path: Path):
    """Yield (question, answer) from a JSONL dataset; answer may be "".

    The answer used to be dropped here. Records carried it in ``next_action``
    and nothing read that field, so the model was trained on questions alone
    and never saw a single answer token — it could not emit "Intel" because
    no such token existed in its vocabulary. Both sides are read now.
    """
    if not path.exists():
        return
    targets = [path] if path.is_file() else [
        f for ext in ("*.jsonl", "*.json") for f in sorted(path.rglob(ext))
    ]
    for fp in targets:
        try:
            for line in fp.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict) or "text" not in obj:
                    continue
                # "response" is the answer; "next_action" is the legacy field.
                answer = obj.get("response") or obj.get("next_action") or ""
                yield str(obj["text"]), str(answer)
        except OSError:
            continue


def _read_texts(path: Path):
    """Yield text payloads from a JSONL/JSON ("text" field) or plain-text file."""
    if not path.exists():
        return
    targets = []
    if path.is_file():
        targets = [path]
    else:
        for ext in ("*.jsonl", "*.json", "*.txt"):
            targets.extend(sorted(path.rglob(ext)))
    for fp in targets:
        try:
            if fp.suffix.lower() in (".jsonl", ".json"):
                for line in fp.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj, dict) and "text" in obj:
                        yield str(obj["text"])
            else:
                yield fp.read_text(encoding="utf-8")
        except OSError:
            continue


def train_tokenizer(input_path: str, vocab_size: int = 32000, output_path: str | None = None) -> dict:
    """Build a frequency-ranked vocabulary from a dataset.

    Returns a summary dict that always echoes the requested ``vocab_size``.
    Missing input paths yield an empty learned vocab (no error). If
    ``output_path`` is given, the vocab is written there as JSON.
    """
    counter: Counter[str] = Counter()
    for question, answer in _read_pairs(Path(input_path)):
        counter.update(question.split())
        counter.update(answer.split())   # answer vocabulary, previously absent

    # Reserve slots for special tokens; fill the rest by frequency.
    capacity = max(0, vocab_size - len(SPECIAL_TOKENS))
    most_common = [tok for tok, _ in counter.most_common(capacity)]
    vocab = {tok: idx for idx, tok in enumerate(SPECIAL_TOKENS + most_common)}

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(vocab, indent=2), encoding="utf-8")

    return {"vocab_size": vocab_size, "learned": len(vocab)}


def _load_vocab(vocab_path: str) -> dict[str, int]:
    path = Path(vocab_path)
    if not path.exists():
        return {tok: i for i, tok in enumerate(SPECIAL_TOKENS)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {tok: i for i, tok in enumerate(SPECIAL_TOKENS)}


def encode(text: str, vocab: dict[str, int]) -> list[int]:
    """Encode text to token IDs, mapping unknown tokens to <unk>."""
    unk = vocab.get("<unk>", 1)
    return [vocab.get(tok, unk) for tok in text.split()]


def tokenize_dataset(input_path: str, output_path: str, vocab_path: str) -> None:
    """Tokenize a dataset to JSONL of {"ids": [...]} using a saved vocab.

    No-ops silently if the input is missing (returns None).
    """
    in_path = Path(input_path)
    if not in_path.exists():
        return
    vocab = _load_vocab(vocab_path)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    bos = vocab.get("<bos>", 2)
    eos = vocab.get("<eos>", 3)
    sep = vocab.get("<sep>", 4)

    with out.open("w", encoding="utf-8") as fh:
        for question, answer in _read_pairs(in_path):
            # <bos> question <sep> answer <eos> — the separator is what turns a
            # flat language-model stream into supervision for answering. Without
            # it the model only ever learns to continue questions.
            ids = [bos] + encode(question, vocab)
            if answer:
                ids += [sep] + encode(answer, vocab)
            ids.append(eos)
            fh.write(json.dumps({"ids": ids}) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AUTON SLM tokenizer")
    parser.add_argument("--input", required=True, help="dataset file or directory")
    parser.add_argument("--output", required=True, help="vocab JSON output path")
    parser.add_argument("--vocab-size", type=int, default=32000)
    parser.add_argument("--tokenize-to", help="also tokenize the input to this JSONL path")
    args = parser.parse_args(argv)

    summary = train_tokenizer(args.input, args.vocab_size, args.output)
    print(json.dumps(summary, indent=2))
    if args.tokenize_to:
        tokenize_dataset(args.input, args.tokenize_to, args.output)
        print(f"tokenized -> {args.tokenize_to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
