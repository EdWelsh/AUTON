"""Plan and analyse a long unscripted session against the booted OS.

Phase 7 exists to catch what the Phase 6 rubric cannot. A 50-prompt eval scores
independent single-shot answers; a 20-minute session tests properties that only
appear over *duration and state*:

  consistency  the same question, asked twice far apart, gets the same answer
  statefulness a change made early is still true late
  stability    answers do not degrade as the session grows
  novelty      input nobody anticipated (here: shell commands at a chat prompt)

Those four are machine-checkable without human judgement, which is what makes
this automatable. What is NOT automated is a person's surprise — see the phase
report for what that costs.

Turn sources, in order of independence from this repo's authors:
  1. gemma4-generated user turns (tests/sessions/generated-turns.jsonl) — the
     host model has never seen our corpus or eval set.
  2. Planted probes at fixed positions, which is the only way to test
     consistency and state deliberately.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVAL_PROMPTS = ROOT / "tests" / "eval" / "prompts.jsonl"
CORPUS = ROOT / "SLM" / "datasets" / "os_chat.jsonl"
GENERATED = ROOT / "tests" / "sessions" / "generated-turns.jsonl"

PROMPT_MARK = "auton> "


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9: ]+", "", text.lower()).strip()


def _known_inputs() -> set[str]:
    """Everything the model was trained on or is evaluated against.

    A session turn that duplicates one of these measures recall, not discovery,
    so generated turns that collide are dropped.
    """
    known = set()
    if EVAL_PROMPTS.exists():
        for line in EVAL_PROMPTS.read_text().splitlines():
            if line.strip():
                known.add(normalize(json.loads(line)["prompt"]))
    if CORPUS.exists():
        for line in CORPUS.read_text().splitlines():
            if line.strip():
                known.add(normalize(json.loads(line)["text"]))
    return known


# Probes planted at fixed positions. Each pair tests one property the eval
# cannot: the same question far apart, or a state change and a later read.
CONSISTENCY_PROBE = "what is my ip"
STATE_SET = "set hostname sessionbox"
STATE_READ = "what is my hostname"
STATE_RESTORE = "set hostname auton"


def plan_turns(limit: int = 60) -> list[dict]:
    """Build the turn plan: planted probes interleaved with generated turns."""
    known = _known_inputs()
    generated = []
    if GENERATED.exists():
        for line in GENERATED.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if normalize(row["text"]) in known:
                continue          # already trained on or evaluated — not discovery
            generated.append(row)

    turns: list[dict] = []

    def add(text, kind, note=""):
        turns.append({"n": len(turns), "text": text, "kind": kind, "note": note})

    # Early consistency + state anchors.
    add(CONSISTENCY_PROBE, "consistency-a", "same question repeated near the end")
    add(STATE_SET, "state-set", "state change; must still hold late in the session")

    half = max(1, len(generated) // 2)
    for row in generated[:half]:
        add(row["text"], "generated", row.get("persona", ""))

    # Mid-session state read: does the early change survive?
    add(STATE_READ, "state-read", "expects sessionbox, set many turns earlier")

    for row in generated[half:]:
        add(row["text"], "generated", row.get("persona", ""))

    # Late consistency: identical to turn 0.
    add(CONSISTENCY_PROBE, "consistency-b", "must match consistency-a exactly")
    add(STATE_READ, "state-read-late", "expects sessionbox still")
    add(STATE_RESTORE, "state-restore", "leave the machine as we found it")

    return turns[:limit]


def extract(log: str, turns: list[dict]) -> dict[int, str]:
    """Map turn index -> the reply block, anchored to the prompt echo."""
    lines = log.splitlines()
    answers: dict[int, str] = {}
    pos = 0
    for turn in turns:
        echo_at = -1
        for i in range(pos, len(lines)):
            if PROMPT_MARK + turn["text"] in lines[i]:
                echo_at = i
                break
        if echo_at < 0:
            answers[turn["n"]] = ""
            continue
        block = []
        for line in lines[echo_at + 1:]:
            if PROMPT_MARK in line:
                break
            block.append(line)
        answers[turn["n"]] = "\n".join(block).strip()
        pos = echo_at + 1
    return answers


FALLBACK = "I am AUTON, an operating system"
RULE_FALLBACK = "I can identify PCI devices"


def analyse(turns: list[dict], answers: dict[int, str]) -> dict:
    """Check the four session properties and collect novel inputs."""
    by_kind = {t["kind"]: t for t in turns}
    findings: list[dict] = []

    def get(kind):
        t = by_kind.get(kind)
        return (t, answers.get(t["n"], "")) if t else (None, "")

    # 1. Consistency — same question, ~50 turns apart.
    ta, a = get("consistency-a")
    tb, b = get("consistency-b")
    if ta and tb:
        same = a.strip() == b.strip()
        findings.append({
            "property": "consistency",
            "ok": same,
            "detail": f"turn {ta['n']} vs {tb['n']}: "
                      + ("identical" if same else f"{a[:48]!r} vs {b[:48]!r}"),
        })

    # 2. Statefulness — a change made early, read much later.
    for kind in ("state-read", "state-read-late"):
        t, ans = get(kind)
        if t:
            held = "sessionbox" in ans
            findings.append({
                "property": "statefulness",
                "ok": held,
                "detail": f"turn {t['n']}: "
                          + ("hostname change held" if held
                             else f"lost the hostname set earlier — {ans[:56]!r}"),
            })

    # 3. Stability — does the answered rate fall off as the session grows?
    gen = [t for t in turns if t["kind"] == "generated"]
    if gen:
        mid = len(gen) // 2
        def answered(rows):
            return sum(1 for t in rows if answers.get(t["n"], "").strip()) / max(1, len(rows))
        first, second = answered(gen[:mid]), answered(gen[mid:])
        findings.append({
            "property": "stability",
            "ok": second >= first - 0.15,
            "detail": f"answered {first:.0%} in the first half, {second:.0%} in the second",
        })

    # 4. Novelty — inputs nobody anticipated, and how the OS met them.
    novel = []
    for t in gen:
        ans = answers.get(t["n"], "")
        novel.append({
            "text": t["text"],
            "answer": ans,
            "empty": not ans.strip(),
            "fell_back": FALLBACK in ans or RULE_FALLBACK in ans,
        })

    return {
        "turns": len(turns),
        "answered": sum(1 for v in answers.values() if v.strip()),
        "findings": findings,
        "novel": novel,
    }
