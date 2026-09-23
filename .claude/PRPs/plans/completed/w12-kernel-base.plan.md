# Plan: A Named Kernel Base

## Summary
Every generation experiment needs a starting tree, and none is named. w11's F6 was seeded from
`kernel-reference-v1`, which predates F4's static-IP `setup.c` and weak `service_main`. That
produced a false `[gate: link closure] dhcp_run` that no agent could have avoided. This plan
tags the correct tree as `kernel-base-v2`, adds one command that materialises it outside the
repo, and repoints the `restore the reference` hint in six scripts. `kernels/` stays deleted.

## User Story
As whoever runs a generation experiment or a boot test, I want one command that produces the
agreed starting tree, so that a gate refusal is about the generated code and never about which
tag I happened to extract.

## Problem → Solution
Two candidate bases, one wrong, chosen by hand; six scripts advise the wrong one →
`kernel-base-v2` tagged at `5fb2777^`'s tree; `scripts/kernel-base.sh <dir>` extracts it;
every hint and default points at it; a test proves the base passes every gate short of the
service's own sources.

## Metadata
- **Complexity**: Small
- **Source PRD**: none. `prds/ELIGIBILITY.md` §2
- **PRD Phase**: blocks factory F6/F7+, driver implementations, intent-G/H
- **Estimated Files**: 9

---

## UX Design
```
Before:  git archive kernel-reference-v1 kernels/x86_64 | tar -x   (the wrong base, silently)
         build_service.py tftp → [gate: link closure] no stub signature for: dhcp_run
After:   scripts/kernel-base.sh /tmp/ws        → /tmp/ws: kernel-base-v2 (5fb2777^), 51 files
         build_service.py tftp --tree /tmp/ws  → [gate: build] undefined: tftp_serve   (the agent's job)
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| "no kernel tree" hint in 6 scripts | `git checkout kernel-reference-v1 -- kernels/` | `scripts/kernel-base.sh kernels/x86_64` | restoring into the repo stays possible; the tree is still gitignored |
| experiment workspaces | hand-extracted | `kernel-base.sh <dir> --git` | `--git` initialises a repo for `GitWorkspace` |

---

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `.claude/PRPs/reports/w11-factory-agent-authored-service-report.md` | "Gates, and a setup error" | why the tag was wrong |
| P0 | `scripts/build-iso.sh` | 10-25 | the hint pattern, repeated in `run-acceptance.sh:12-18`, `auton-boot.sh:15-22`, `auton-boot-native.sh:22-28`, `eval.sh:54-61`, `session.sh:43-52` |
| P1 | `agent/tools/build_service.py` | 256-275, 376 | the sources gate; `--tree` default |
| P1 | `agent/tests/unit/test_scaffold.py` | 110-125 | `TestTheRepoContainsNoKernel` must stay true |
| P2 | `agent/kernel_spec/reference/README.md` | all | "a reference, not a product" |

## Patterns to Mirror

### ERROR_HANDLING (absent tree, stated plainly)
// SOURCE: scripts/auton-boot.sh:15-22
```bash
if [ ! -d "$KDIR/kernel" ]; then
	echo "no kernel tree at ${KDIR#"$ROOT"/}" >&2
	echo "AUTON's premise is that the agents write it (README.md). Generate one," >&2
	echo "or restore the reference: git checkout kernel-reference-v1 -- kernels/" >&2
	exit 2
fi
```

### SCRIPT_SHAPE
// SOURCE: scripts/measure_authorship.sh (w11): a thin wrapper, `set -uo pipefail`, ROOT from `$0`.

### TEST_STRUCTURE
// SOURCE: agent/tests/unit/test_scaffold.py:80-95: build against `tmp_path`, `pytest.raises(GateFailure, match=...)`.

---

## Files to Change
| File | Action | Justification |
|---|---|---|
| git tag `kernel-base-v2` | CREATE | annotated, on `5fb2777^`, message citing the w11 report |
| `scripts/kernel-base.sh` | CREATE | `kernel-base.sh <dir> [--git] [--rev TAG]`, via `git archive <tag> kernels/x86_64` into `<dir>` |
| `scripts/{build-iso,run-acceptance,auton-boot,auton-boot-native,eval}.sh` | UPDATE | the hint names `kernel-base.sh` |
| `agent/kernel_spec/reference/README.md` | UPDATE | a "Bases" section: v1 = the retired tree, v2 = v1 + F4's factory hooks, and what each is for |
| `agent/tests/unit/test_kernel_base.py` | CREATE | the base passes spec/capabilities/sources/link-closure for `tftp` and fails only at `undefined: tftp_serve` |
| `.github/workflows/portability.yml` | UPDATE | `fetch-tags: true` on checkout, or the test skips in CI |

## NOT Building
- Putting a kernel back in the repo. `TestTheRepoContainsNoKernel` stays green.
- A generated-from-nothing base. Whether the loop can produce the whole tree is a later
  experiment; this plan names the base the *service* experiments assume.

---

## Step-by-Step Tasks

### Task 1: Tag the base
- **ACTION**: `git tag -a kernel-base-v2 5fb2777^ -m "…"` and push the tag.
- **GOTCHA**: The tag must point at a commit whose `kernels/x86_64` has F4's `setup.c` (+22) and `kernel_main.c` (+10). Verify with `git diff --stat kernel-reference-v1 kernel-base-v2 -- kernels/x86_64`, which should show exactly those two files.
- **VALIDATE**: `git archive kernel-base-v2 kernels/x86_64 | tar -t | wc -l` gives 51 entries.

### Task 2: `scripts/kernel-base.sh`
- **IMPLEMENT**: Extract `kernels/x86_64` from `--rev` (default `kernel-base-v2`) and flatten it so `<dir>/Makefile` exists. Refuse a non-empty `<dir>`. With `--git`, run `git init -b main` and commit `base: kernel-base-v2`. Print the rev and the file count.
- **GOTCHA**: A shallow clone has no tags, so fail naming `git fetch --tags`. Do not fall back to v1.
- **VALIDATE**: `scripts/kernel-base.sh "$(mktemp -d)/ws" --git` then `make -C …/ws iso` succeeds.

### Task 3: Point every hint at it
- **ACTION**: Replace the `git checkout kernel-reference-v1 -- kernels/` line in the five scripts with `scripts/kernel-base.sh kernels/x86_64`.
- **VALIDATE**: `grep -rn kernel-reference-v1 scripts/` returns nothing.

### Task 4: The test that would have caught w11's setup error
- **IMPLEMENT**: `test_kernel_base.py` extracts the base into `tmp_path` and calls `build("tftp", tree)`. It expects `GateFailure` matching `tftp_serve`, and **not** `link closure`. A second test asserts v1 *does* fail at link closure, which pins why v2 exists. Skip when the tag is absent.
- **GOTCHA**: `build()` needs `x86_64-elf-gcc`. Skip, naming the missing compiler, as the other build tests do.
- **VALIDATE**: passes locally; skips cleanly without the tag.

### Task 5: Document the bases
- **ACTION**: Add a "Bases" section to `reference/README.md`.
- **VALIDATE**: it names both tags, the 31-line difference, and "experiments use v2".

## Testing Strategy
| Test | Input | Expected |
|---|---|---|
| v2 + tftp | base, no service sources | `GateFailure` naming `tftp_serve` |
| v1 + tftp | old tag | `GateFailure` naming `link closure` / `dhcp_run` |
| script, non-empty dir | existing file | exit 2, message |
| script, no tag | shallow clone | exit 2, names `git fetch --tags` |

## Validation Commands
```bash
scripts/kernel-base.sh "$(mktemp -d)/ws" --git
cd agent && ../.venv/bin/python -m pytest tests/unit/test_kernel_base.py tests/unit/test_scaffold.py -q
cd agent && ../.venv/bin/python -m pytest -q
```

## Acceptance Criteria
- [ ] `kernel-base-v2` tagged and pushed
- [ ] One command produces the base; experiments use it
- [ ] No script recommends v1
- [ ] A test pins that v2 fails only for missing service sources

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The tag is not pushed and CI skips | M | L | Task 1 pushes it; the workflow fetches tags |
| Someone commits the extracted tree | L | M | `kernels/` stays gitignored; the scaffold test guards the index |
