"""Dataset preprocessing and analysis utilities.

Operates on JSONL datasets of OS-task samples (see README "Dataset Structure"):
each line is a JSON object with at least a "text" field.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _iter_text_files(path: Path):
    """Yield .jsonl/.json/.txt files under a path (file or directory)."""
    if path.is_file():
        yield path
    elif path.is_dir():
        for ext in ("*.jsonl", "*.json", "*.txt"):
            yield from sorted(path.rglob(ext))


def _iter_texts(file_path: Path):
    """Yield the text payload of each record in a dataset file."""
    suffix = file_path.suffix.lower()
    try:
        if suffix in (".jsonl", ".json"):
            with file_path.open(encoding="utf-8") as fh:
                for line in fh:
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
            yield file_path.read_text(encoding="utf-8")
    except OSError:
        return


def analyze_dataset(dataset_path: str) -> dict:
    """Analyze dataset statistics.

    Returns counts of files, whitespace tokens, and unique-token vocab size.
    A nonexistent path yields zero counts.
    """
    path = Path(dataset_path)
    files = 0
    tokens = 0
    vocab: set[str] = set()

    for file_path in _iter_text_files(path):
        files += 1
        for text in _iter_texts(file_path):
            words = text.split()
            tokens += len(words)
            vocab.update(words)

    return {
        "files": files,
        "tokens": tokens,
        "vocab_size": len(vocab),
    }


def clean_dataset(input_path: str, output_path: str) -> None:
    """Clean and preprocess a dataset.

    Deduplicates records by their normalized "text", drops empty/whitespace-only
    samples, and writes the result as JSONL. No-ops silently if the input is
    missing (operates via side effects, returns None).
    """
    in_path = Path(input_path)
    if not in_path.exists():
        return

    seen: set[str] = set()
    cleaned: list[dict] = []
    for file_path in _iter_text_files(in_path):
        for text in _iter_texts(file_path):
            norm = " ".join(text.split())
            if not norm or norm in seen:
                continue
            seen.add(norm)
            cleaned.append({"text": norm})

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for rec in cleaned:
            fh.write(json.dumps(rec) + "\n")


def split_dataset(input_path: str, output_dir: str, train_ratio: float = 0.9) -> dict:
    """Split a JSONL dataset into train/validation files.

    Returns a summary dict with the record counts written to each split.
    """
    in_path = Path(input_path)
    records: list[str] = []
    for file_path in _iter_text_files(in_path):
        if file_path.suffix.lower() in (".jsonl", ".json"):
            with file_path.open(encoding="utf-8") as fh:
                records.extend(line for line in fh if line.strip())

    cutoff = int(len(records) * train_ratio)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "train.jsonl").write_text("".join(records[:cutoff]), encoding="utf-8")
    (out / "val.jsonl").write_text("".join(records[cutoff:]), encoding="utf-8")
    return {"train": cutoff, "val": len(records) - cutoff}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AUTON SLM dataset builder")
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="report dataset statistics")
    p_analyze.add_argument("path")

    p_clean = sub.add_parser("clean", help="dedupe + normalize into JSONL")
    p_clean.add_argument("--input", required=True)
    p_clean.add_argument("--output", required=True)

    p_split = sub.add_parser("split", help="train/val split")
    p_split.add_argument("--input", required=True)
    p_split.add_argument("--output", required=True)
    p_split.add_argument("--train-ratio", type=float, default=0.9)

    args = parser.parse_args(argv)

    if args.command == "analyze":
        print(json.dumps(analyze_dataset(args.path), indent=2))
    elif args.command == "clean":
        clean_dataset(args.input, args.output)
        print(f"cleaned -> {args.output}")
    elif args.command == "split":
        summary = split_dataset(args.input, args.output, args.train_ratio)
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
