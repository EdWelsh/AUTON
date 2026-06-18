# AUTON operator — the chat *is* the OS

Speak a goal; AUTON plans it with a model and does the steps with real tools, in
the background, asking before anything irreversible. This is the AUTON OS vision:
you operate the computer by talking to it.

```bash
auton-do "download the budget sheet from https://xyz.com/budget.xlsx, \
          set B2 to 1234 and email it to boss@example.com"
```

AUTON downloads the file, edits it (openpyxl), drafts the email, **shows it to
you and waits for 'y'**, then sends it (SMTP). Verified end-to-end live with a
local Ollama model driving the tools.

## The brain is pluggable

The model that plans is swappable — that's the design:

| You say / configure | Brain |
|---------------------|-------|
| default | local Ollama (`agent/config/auton.toml` `[llm].model`, e.g. `ollama/llama3.1:8b`) |
| `--model "use chatgpt"` | OpenAI (needs `OPENAI_API_KEY`) |
| `--model "use claude"` | Anthropic (needs `ANTHROPIC_API_KEY`) |
| (no model reachable) | deterministic planner — parses the goal and runs the steps offline |

The on-device kernel SLM is the north-star brain; it's too small for reliable
multi-step tool-use today, so the runtime falls back exactly like the kernel's
neural→rule-engine path.

## Tools (real, headless, sandboxed to a per-task workspace)

`download_file` · `read_spreadsheet` · `update_spreadsheet` · `send_email`
(gated by confirmation). Adding a tool = one function + one JSON schema in
`tools.py`; the model can immediately use it.

## Autonomy

Plan + **confirm before irreversible** is the default: reversible work runs
autonomously; sending email / paying / deleting stops for your explicit yes
(`--yes` to auto-approve, used by tests). See `approval.py`.

## Flags

```
auton-do "<goal>" [--brain auto|llm|rule] [--model "use chatgpt"] [--yes]
                  [--smtp-host H] [--smtp-port P] [--from addr]
```
