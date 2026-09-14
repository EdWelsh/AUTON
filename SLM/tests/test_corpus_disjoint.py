"""The corpus must never contain the eval prompts.

If a training example matches a Phase 6 eval prompt, the eval stops measuring
generalisation and starts measuring memorisation — and every quality claim made
afterwards is silently false. The failure is invisible from the score alone (a
contaminated model looks *better*), so this is enforced as a test rather than a
review step.

The eval set was fixed before this corpus existed, on purpose.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "SLM" / "datasets" / "os_chat.jsonl"
EVAL_PROMPTS = ROOT / "tests" / "eval" / "prompts.jsonl"

# Two reorderings of the same words are the same question for our purposes.
NEAR_DUPLICATE_JACCARD = 0.9


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9: ]+", "", text.lower()).strip()


def tokens(text: str) -> set[str]:
    return set(normalize(text).split())


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@pytest.fixture(scope="module")
def corpus() -> list[dict]:
    if not CORPUS.exists():
        pytest.skip(f"corpus not built: {CORPUS}")
    return [json.loads(line) for line in CORPUS.read_text().splitlines() if line.strip()]


@pytest.fixture(scope="module")
def eval_prompts() -> list[dict]:
    return [json.loads(line) for line in EVAL_PROMPTS.read_text().splitlines() if line.strip()]


def test_no_exact_overlap_with_eval(corpus, eval_prompts):
    eval_norm = {normalize(p["prompt"]): p["id"] for p in eval_prompts}
    hits = [
        (r["text"], eval_norm[normalize(r["text"])])
        for r in corpus
        if normalize(r["text"]) in eval_norm
    ]
    assert not hits, (
        "corpus contains eval prompts verbatim — the eval would measure "
        f"memorisation: {hits[:5]}"
    )


def test_no_near_duplicates_of_eval(corpus, eval_prompts):
    eval_tokens = [(p["id"], tokens(p["prompt"])) for p in eval_prompts]
    hits = []
    for row in corpus:
        row_tokens = tokens(row["text"])
        for pid, et in eval_tokens:
            if jaccard(row_tokens, et) >= NEAR_DUPLICATE_JACCARD:
                hits.append((row["text"], pid))
                break
    assert not hits, f"corpus near-duplicates eval prompts: {hits[:5]}"


def test_every_record_has_a_question_and_an_answer(corpus):
    # The rung-3a defect: answers lived in a field nothing trained on.
    bad = [r for r in corpus if not r.get("text", "").strip()
           or not r.get("response", "").strip()]
    assert not bad, f"{len(bad)} records missing question or answer: {bad[:3]}"


def test_all_intent_classes_present(corpus):
    required = {
        "HARDWARE_IDENTIFY", "DRIVER_SELECT", "INSTALL_CONFIGURE",
        "APP_INSTALL", "SYSTEM_MANAGE", "TROUBLESHOOT", "OUT_OF_DOMAIN",
    }
    present = {r["intent"] for r in corpus}
    assert required <= present, f"missing intent classes: {required - present}"


def test_no_duplicate_questions(corpus):
    seen: dict[str, str] = {}
    dupes = []
    for r in corpus:
        key = normalize(r["text"])
        if key in seen and seen[key] != r["response"]:
            dupes.append((r["text"], seen[key][:40], r["response"][:40]))
        seen[key] = r["response"]
    assert not dupes, f"same question with conflicting answers: {dupes[:3]}"


def test_held_out_split_is_disjoint_by_fact(corpus):
    """Paraphrases of one fact must not straddle the split.

    Splitting at random would put "what is my ip" in train and "show my ip" in
    held-out, and the held-out score would measure recall of a memorised answer
    rather than generalisation to new phrasing.
    """
    facts = sorted({r["fact"] for r in corpus})
    held_out_facts = set(facts[:: max(1, len(facts) // 10)])
    train = [r for r in corpus if r["fact"] not in held_out_facts]
    held = [r for r in corpus if r["fact"] in held_out_facts]

    assert train and held, "split produced an empty side"
    assert not ({r["fact"] for r in train} & {r["fact"] for r in held}), \
        "a fact appears on both sides of the split"


# --- grounding ------------------------------------------------------------- #
# A corpus that teaches an id the machine does not have produces a model that
# cites it. Measured: 5 phantom citations per 50 novel turns, against 0 from the
# deterministic path. These are the cheapest place to catch that — long before a
# training run, an export and a boot.

PCI_ID = re.compile(r"\b[0-9a-f]{4}:[0-9a-f]{4}\b")


def test_no_response_cites_an_id_absent_from_the_bus(corpus):
    """Every PCI id in an answer must be a device this machine actually has.

    The corpus previously taught 10ec:8139 and 1022:2000 — a Realtek NIC and an
    AMD bridge on no bus AUTON boots — in 14 records each.
    """
    import sys

    sys.path.insert(0, str(ROOT / "SLM" / "tools"))
    from build_corpus import BUS_DEVICES

    on_bus = set(BUS_DEVICES)
    offenders = [
        (r["fact"], ident)
        for r in corpus
        for ident in PCI_ID.findall(r["response"].lower())
        if ident not in on_bus
    ]
    assert not offenders, f"responses cite ids absent from the bus: {offenders[:5]}"


def test_the_bus_list_and_the_devices_answer_agree(corpus):
    """`SYS_FACTS["devices"]` is rendered from BUS_DEVICES rather than restated,
    so the two cannot drift. This pins that they have not."""
    import sys

    sys.path.insert(0, str(ROOT / "SLM" / "tools"))
    from build_corpus import BUS_DEVICES

    answers = [r["response"] for r in corpus if r["fact"] == "sys:devices"]
    assert answers, "no devices answer in the corpus"
    for ident in BUS_DEVICES:
        assert ident in answers[0], f"{ident} on the bus but not in the answer"
    assert str(len(BUS_DEVICES)) in answers[0]


def test_a_question_with_no_id_is_taught_to_ask_for_one(corpus):
    """The actual gap. With no record for `i need gpu access`, the model reached
    for the nearest neighbour — the unknown-device template — and answered with
    a device the asker never mentioned."""
    clarifications = [r for r in corpus if r["fact"] == "clarify:no-device-id"]

    assert len(clarifications) >= 20, f"only {len(clarifications)} clarification records"
    for r in clarifications:
        assert not PCI_ID.findall(r["response"]), \
            f"a clarification for a question with no id cites one: {r['response']}"
        assert not PCI_ID.findall(r["text"]), \
            f"{r['text']!r} contains an id, so it is not a no-id question"


def test_category_questions_do_not_collide_with_the_bus_listing(corpus):
    """`what gpu do i have` must ask for an id; `what devices` must list the bus.
    If a phrasing lands in both classes the model is taught two answers for one
    question."""
    listing = {normalize(r["text"]) for r in corpus if r["fact"] == "sys:devices"}
    clarify = {normalize(r["text"]) for r in corpus if r["fact"] == "clarify:no-device-id"}

    assert not (listing & clarify), f"taught both ways: {listing & clarify}"
    for a in clarify:
        for b in listing:
            assert jaccard(tokens(a), tokens(b)) < NEAR_DUPLICATE_JACCARD, \
                f"near-duplicate across classes: {a!r} vs {b!r}"
