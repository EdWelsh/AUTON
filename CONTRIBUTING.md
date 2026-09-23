# Contributing to AUTON

Thanks for looking. Bug reports, specification issues and questions are as
useful here as code — arguably more so, because most of this repository is the
apparatus that *judges* generated code, and apparatus with a blind spot is worse
than none.

Before anything else, two facts that shape everything below:

1. **The kernel is not written by hand.** If you are tempted to implement a
   subsystem yourself, that is the one contribution the project cannot take.
   Improve the specification or the gate that judges it instead.
2. **This is a source-available project, not an open-source one.** See
   [Licensing of contributions](#licensing-of-contributions).

## The rule that matters most: a test must be able to fail

A suite that cannot fail is not evidence. This has bitten this project more than
once, and the scars are in the code:

- A path-traversal suite passed against a resolver with **no checks at all**,
  because every hostile path it tried was absent from the fake filesystem.
- A parity harness compared kernel output to reference output when **both were
  empty**, and reported `ALL PASS`.
- A gate guarded on one condition while its own skip message named a different
  one, so it asserted `0 > 0` on a fresh clone.

So, for any test you add or change:

- **Score it by injecting the bug.** Break the thing on purpose, confirm the
  test fails, put it back. If it does not fail, the test is decoration. 10 of
  the 22 host suites in [`tests/kernel/`](tests/kernel/) are scored this way, and
  a new one should be scored before it is relied on.
- **Never let absence read as success.** Empty output compared with empty output
  is a load failure, not agreement.
- **Say why a skip is a skip.** A skipped test must state the missing thing —
  "no errata documents cached" — not vanish quietly. Silence is not a pass.

## Gate exit codes

Host gates use three exit codes, and keeping them apart is the point:

| Code | Meaning |
|---|---|
| `0` | pass |
| `1` | generated, but wrong |
| `2` | not generated |

A missing implementation must never read as a failing one, and a suite that did
not run has found nothing. If you add a gate, follow this and give it a
`--self-test` mode that proves the suite against a reference implementation.

## Don't let a gate demand what it doesn't gate

Twice now a gate has been unpassable for reasons unrelated to the code it
judges: the TFTP gate shipped a stub that shadowed `libk`, so no conformant
server could compile; the memory-manager gate required a header belonging to a
different subsystem that was not in the run's scope. Both hid real results.

If your gate needs something from outside its subsystem, supply a
spec-derived stand-in and say so on stderr — don't refuse.

## Tests that depend on the machine

A test that passes only on the machine that wrote it is a liability. The usual
culprits here are gitignored caches (`.cache/vendor/`), local configuration
(`agent/config/auton.toml`) and generated trees (`kernels/`).

The cheapest check is a clean clone:

```bash
git clone --no-local . /tmp/clean && cd /tmp/clean
# then run the suite you touched
```

Likewise, sanitizers differ by platform: ASan runs LeakSanitizer on Linux and
**cannot** on macOS. A green local run does not mean a leak-free one.

## Development setup

```bash
git clone https://github.com/EdWelsh/AUTON.git
cd AUTON

# Orchestrator (Python >= 3.11)
cd agent && pip install -e . && cd ..

# Host control plane (Python >= 3.10)
cd controlplane && pip install -e ".[dev,ui]" && cd ..

# A kernel tree to build or point gates at — `kernels/` is generated output
# and is not in the repository
scripts/kernel-base.sh kernels/x86_64
```

### Running things

```bash
pytest agent/tests/unit/                     # orchestrator
pytest agent/tests/integration/              # workflows
PYTHONPATH=SLM pytest SLM/tests/             # SLM pipeline
cd controlplane && pytest                    # control plane
cd agent/tools && cargo test                 # Rust tooling

tests/kernel/run_mm_test.sh --self-test      # a gate against its reference
KERNEL_TREE=/tmp/tree tests/kernel/run_mm_test.sh   # a gate against a tree
```

`scripts/preflight.sh` checks the host has the toolchain and enough free disk
before anything long runs.

Note that `scripts/run-acceptance.sh` exits non-zero today on purpose: one
specified marker is not yet generated. See
[`docs/E2E-EXPECTED.yaml`](docs/E2E-EXPECTED.yaml), which records the expected
red and which CI checks — so a *new* failure is caught, and so is a stale
expectation that no longer matches reality.

## Style

- **Python** — ruff, targeting py311. Type hints on public functions.
- **C** — freestanding, `-ffreestanding -std=gnu11`, no libc in kernel code.
  Integer arithmetic only where a specification says so; no `float`/`double` in
  conformance paths.
- **Shell** — bash, `set -uo pipefail`. `timeout(1)` is not on macOS; use
  `auton_timeout` from `scripts/lib/toolchain.sh`.
- **Comments explain *why*.** The repository is full of comments recording a
  specific defect and the reasoning that fixed it. That is deliberate. A comment
  restating the code is noise; one naming the bug that made the code look odd is
  the most valuable line in the file.

## Commit messages

```
<type>(<scope>): <what changed, and enough of why to be worth reading>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `perf`, `ci`.

Subject lines here are written to be read as a history, not as a changelog.
Prefer the specific over the generic:

```
fix(tftp gate): the stub shadowed libk, so no conformant server could compile
test(tftp): an ACK for a block never sent must be ignored
```

over `fix: bug in gate`. If a change fixes something subtle, the body should say
what the failure looked like, so the next person recognises it.

## Pull requests

1. Branch from `main`.
2. Make the change, and score any new test by injecting the bug it catches.
3. Run the suites your change touches; run a clean clone if you touched anything
   that might depend on local state.
4. Fill in the PR template, including how you verified — and say plainly if you
   could not verify something. "CI is the check for this, because LeakSanitizer
   does not run on macOS" is a good answer. Implying you proved something you
   did not is the one thing that will get a PR rejected outright.

CI runs `controlplane` and `portability` on every push. Both must be considered;
a leg that was already red before your change should be called out rather than
quietly inherited.

## Reporting bugs

Use the issue templates. For anything security-related, do **not** open an issue
— see [SECURITY.md](SECURITY.md).

## Licensing of contributions

AUTON is distributed under the [AUTON Source Available License](LICENSE.md),
which permits personal, educational, academic and non-production use, and
requires a commercial licence or public attribution for production and
enterprise use. It is **not** an OSI-approved open-source licence.

By submitting a contribution you agree that it is licensed under those same
terms. If that does not work for you, please open an issue to discuss before
spending time on a change.

## Code of conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
