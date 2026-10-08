# w23 A3: w22 fully agent-driven on `qwen3.5:27b-coding-mxfp8`. Result: 1 of 3

**Pre-registration:** [w23-a3-fully-agent-driven-preregistration.md](w23-a3-fully-agent-driven-preregistration.md).
**Run:** `.artifacts/w23-a3/`, 2026-10-08, `scripts/app_to_env.py`, no `--record`, no `--recipe`.

| Subject | Ends at | Detail |
|---|---|---|
| node-js-getting-started | **`ablate` passed. Fully agent-driven** | analyst 5,442 s, packager 1,168 s (image with 124 extras), observe 11 facts, regate 0 missing, probe WORKED, ablation **9 of 12 load-bearing**; over-claimed `npm:jest`, `path:/etc/localtime`, `path:/etc/ssl/openssl.cnf` |
| flask `examples/javascript` | `packager` | the Analyst merged a record in 5,004 s, but declared `runtime:python-3.10`, and `bases.yaml` lists no base for it (listed: glibc-elf, node-22, python-3.12, python-3.13, static-elf). The Packager could not satisfy the gate in 7,200 s |
| traefik/whoami (Go) | `analyst` | no merged record in the 2 h budget (exit 75) |

**Headline.** The PRD's metric, applications compiled to a running, ablated environment with no
human input, moves from **0 of 3 to 1 of 3**. The 9b's 0 of 3 was a capability gap; the larger
model closes part of it.

## Against the predictions

- All three analysed: **missed** (whoami timed out).
- whoami fails at packaging: **missed**; it never got that far.
- Node over-claims: **held** (three, found by ablation, which is what it is for).

## Findings

1. **Vocabulary and bases disagree.** `capabilities.yaml` names `runtime:python-3.10` and `3.11`,
   but `bases.yaml` has no base for them. A record can be valid and unbuildable. Either the index
   should only name runtimes with a base, or the Analyst should be told which runtimes are
   buildable. **New item C5.**
2. **`npm:jest` is a dev dependency**, claimed as required. The ablation caught it; the Analyst
   prompt could say that development dependencies are not requirements (the C2 question, now with
   evidence from a real subject).
3. **whoami analysis is slow, not wrong:** budget, not a refusal. Not re-run with a longer budget,
   which would be a different experiment.

## Consequence

The answer to "can local models on this machine do the analysis" is **partly yes**: one real
subject end to end, one blocked by a fixable index gap, one by time. The next levers are C5 and the
prompt (finding 2), and a longer whoami budget as a labelled experiment.

## Continuation: js-example after C5 (2026-10-08, labelled; from the Analyst's own record)

With bases for every indexed runtime, the Packager got past the base gate and wrote a recipe, which
failed the build gate: it `COPY`ed only `js_example/`, and `pip install .` needs the
`pyproject.toml`'s README. That is an agent recipe error, correctly refused by the build gate, not a
gate or vocabulary gap. The subject still ends at `packager`, so **A3 stays at 1 of 3**.

The record itself was weaker than the fixture's: it cites `dependencies = ["flask"]` as the evidence
for `runtime:python-3.10`, which the line does not show. The evidence gate checks that a quote
exists at its line, not that it supports the claim; that is the reviewer's job, and here it passed.
Both are inputs to a prompt-and-reviewer question, not a vocabulary one.
