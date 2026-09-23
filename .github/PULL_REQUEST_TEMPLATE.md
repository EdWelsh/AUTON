<!--
Thanks for contributing. Please read CONTRIBUTING.md if you have not — the rule
that matters most here is that a test must be able to fail.
-->

## What this changes

<!-- What it does, and enough of why to be worth reading. -->

## Why

<!--
If this fixes something subtle, describe what the failure looked like. The next
person to hit it should recognise it from this paragraph.
-->

## How it was verified

<!--
Be specific, and be honest about the limits. Saying "CI is the check for this,
because LeakSanitizer does not run on macOS" is a good answer. Implying you
proved something you did not is the one thing that will get a PR rejected.
-->

```
paste the commands you ran and their results
```

## Checklist

- [ ] Any new or changed test was **scored by injecting the bug it catches** —
      I broke the thing on purpose, confirmed the test failed, and put it back
- [ ] No test can pass by finding nothing (empty vs empty is a load failure,
      not agreement)
- [ ] Any skip states the missing thing, rather than passing quietly
- [ ] Gate exit codes still mean what they claim: `2` not generated, `1`
      generated wrong, `0` pass
- [ ] Run against a clean clone if this could depend on local state — a
      gitignored cache, `agent/config/auton.toml`, or a generated `kernels/` tree
- [ ] Comments explain *why*, and name the defect where one motivated the code
- [ ] Docs updated if behaviour or instructions changed
- [ ] I did not hand-write kernel implementation code (see CONTRIBUTING.md)

## CI

<!--
Both `controlplane` and `portability` run on every push. If a leg was already
red before this change, say so here rather than inheriting it silently — and say
which failures are yours.
-->

## Anything you could not verify

<!--
Genuinely useful. Platform you do not have, a sanitizer that does not run on
your OS, hardware the gate needs. Say it here rather than leaving it implied.
-->
