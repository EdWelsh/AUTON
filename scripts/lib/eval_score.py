"""Extract answers from an AUTON serial log, grade them, and score the run.

Grading is hybrid by design (tests/eval/rubric.md): prompts with a deterministic
answer carry an ``expect`` substring and grade automatically; free-form prompts
are queued for a human, because a machine cannot reliably separate CORRECT from
GARBAGE on an open-ended answer and pretending otherwise would make the number
meaningless.

Human verdicts are cached by (model fingerprint, prompt id, answer hash), so an
unchanged model re-scores without asking anything, and a changed answer
correctly re-queues.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

CORRECT = "correct"
HONEST = "honest_roadmap"
GARBAGE = "garbage"
UNGRADED = "ungraded"

PROMPT_MARK = "auton> "
# The reply the kernel gives when it has not understood; answering an
# answerable question with this is non-responsive (rubric, GARBAGE rule).
FALLBACK = "I can identify PCI devices, recommend drivers, and outline setup"


def load_prompts(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def extract_answers(log: str, prompts: list[dict]) -> dict[str, str]:
    """Map prompt id -> the reply block that followed its echo.

    Anchored to the prompt echo, and scoped to the block before the next
    prompt, for the same reason scripts/transcript.sh is: the boot banner and
    help text quote example commands, so a bare search finds the wrong block.
    """
    lines = log.splitlines()
    answers: dict[str, str] = {}
    pos = 0
    for row in prompts:
        text = row["prompt"]
        echo_at = -1
        for i in range(pos, len(lines)):
            if PROMPT_MARK + text in lines[i]:
                echo_at = i
                break
        if echo_at < 0:
            answers[row["id"]] = ""
            continue
        block: list[str] = []
        for line in lines[echo_at + 1:]:
            if PROMPT_MARK in line:
                break
            block.append(line)
        answers[row["id"]] = "\n".join(block).strip()
        pos = echo_at + 1
    return answers


def auto_grade(row: dict, answer: str) -> str | None:
    """Grade what can be graded mechanically; None means 'ask a human'."""
    if not answer:
        return GARBAGE                      # empty reply — rubric rule 1
    expect = row.get("expect")
    if not expect:
        return None                         # free-form -> human queue
    if expect in answer:
        # Some prompts are answered correctly *by declining*: a roadmap
        # capability or an honest "not in the knowledge base". Scoring those as
        # CORRECT would inflate the headline number and blur the distinction the
        # rubric exists to draw, so the prompt says which bucket a match means.
        return row.get("bucket", CORRECT)
    # An answerable prompt met with the generic fallback is non-responsive.
    if FALLBACK in answer:
        return GARBAGE
    return None     # said something else entirely — a human decides what it was


def cache_key(fingerprint: str, pid: str, answer: str) -> str:
    digest = hashlib.sha256(answer.encode("utf-8")).hexdigest()[:16]
    return f"{fingerprint}|{pid}|{digest}"


def main() -> int:
    log = Path(os.environ["EVAL_LOG"]).read_text(errors="replace")
    prompts = load_prompts(Path(os.environ["EVAL_PROMPTS"]))
    cache_path = Path(os.environ["EVAL_CACHE"])
    fingerprint = os.environ["EVAL_FINGERPRINT"]
    review = os.environ.get("EVAL_REVIEW") == "1"
    json_out = os.environ.get("EVAL_JSON") or ""

    cache: dict[str, str] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text())

    answers = extract_answers(log, prompts)
    results, queued = [], []

    for row in prompts:
        pid = row["id"]
        answer = answers.get(pid, "")
        verdict = auto_grade(row, answer)
        source = "auto"
        if verdict is None:
            key = cache_key(fingerprint, pid, answer)
            if key in cache:
                verdict, source = cache[key], "cached"
            else:
                verdict, source = UNGRADED, "queued"
                queued.append((row, answer))
        results.append(
            {"id": pid, "intent": row["intent"], "prompt": row["prompt"],
             "answer": answer, "verdict": verdict, "graded_by": source}
        )

    if review and queued:
        print(f"\n--- human review: {len(queued)} answers ---")
        print("[c]orrect  [h]onest-roadmap  [g]arbage  [s]kip\n")
        for row, answer in queued:
            print(f"{row['id']}  ({row['intent']})")
            print(f"  Q: {row['prompt']}")
            print(f"  A: {answer or '(no answer)'}")
            if row.get("note"):
                print(f"  note: {row['note']}")
            choice = ""
            while choice not in ("c", "h", "g", "s"):
                choice = (input("  verdict [c/h/g/s]: ").strip().lower() or "s")[:1]
            if choice == "s":
                print()
                continue
            verdict = {"c": CORRECT, "h": HONEST, "g": GARBAGE}[choice]
            cache[cache_key(fingerprint, row["id"], answer)] = verdict
            for r in results:
                if r["id"] == row["id"]:
                    r["verdict"], r["graded_by"] = verdict, "human"
            print()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True))

    total = len(results)
    counts = {b: sum(1 for r in results if r["verdict"] == b)
              for b in (CORRECT, HONEST, GARBAGE, UNGRADED)}
    graded = total - counts[UNGRADED]

    print()
    for r in results:
        flag = {CORRECT: "CORRECT", HONEST: "HONEST ", GARBAGE: "GARBAGE",
                UNGRADED: "  ??   "}[r["verdict"]]
        print(f"{flag}  {r['id']:<8} {r['prompt'][:52]}")

    print()
    print(f"graded {graded}/{total}"
          + (f"  ({counts[UNGRADED]} awaiting review — run with --review)"
             if counts[UNGRADED] else ""))
    if graded:
        pct = lambda n: 100.0 * n / graded  # noqa: E731
        passing = counts[CORRECT] + counts[HONEST]
        print(f"  correct        {counts[CORRECT]:3d}  {pct(counts[CORRECT]):5.1f}%")
        print(f"  honest-roadmap {counts[HONEST]:3d}  {pct(counts[HONEST]):5.1f}%")
        print(f"  garbage        {counts[GARBAGE]:3d}  {pct(counts[GARBAGE]):5.1f}%")
        print(f"  SCORE  correct-or-honest {pct(passing):.1f}%  garbage {pct(counts[GARBAGE]):.1f}%")
        print(f"  BAR    >=70% correct-or-honest and <10% garbage -> "
              f"{'PASS' if pct(passing) >= 70 and pct(counts[GARBAGE]) < 10 else 'FAIL'}")

    if json_out:
        Path(json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(json_out).write_text(json.dumps(
            {"fingerprint": fingerprint, "total": total, "graded": graded,
             "counts": counts, "results": results}, indent=2))
        print(f"  json -> {json_out}")

    # Ungraded answers are not failures; they are unanswered questions.
    return 0 if counts[UNGRADED] == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
