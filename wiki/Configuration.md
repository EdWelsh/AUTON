# Configuration

`agent/config/auton.toml` (copy it from `auton.toml.example`; it is gitignored because it can
hold API keys). The launchers write their own copy per run, so a run's configuration is
archived with it.

| Section | Key settings |
|---|---|
| `[llm]` | `model`: a LiteLLM id (`anthropic/…`, `openai/…`), `ollama_chat/<model>`, or `claude-cli/<model>` for the Claude subscription through Claude Code; `max_tokens`, `temperature`, request timeout, context length |
| `[llm.cost]` | `max_cost_usd`, `warn_at_usd` (API providers) |
| `[llm.api_keys]`, `[llm.endpoints]` | provider keys and endpoints, or use environment variables |
| `[agents]` | `developer_count` (4), `reviewer_count` (1), `tester_count` (1), `training_agent_count` (2), **`specialists`** (`"all"`, a list of ids, or `false`) |
| `[agents.models]` | a model per role (`manager = "…"`) |
| `[workspace]` | `path`: where the run's git workspace is; the launchers point it into `.artifacts/` |
| `[kernel]` | `arch`: `x86_64`, `aarch64`, `riscv64` |
| `[validation]` | build and test timeouts; composition checks |
| `[logging]` | level and log paths |
| `[orchestrator]` | `max_iterations`, review rounds |
| **`[workflow]`** | `mode`: `kernel_build` (default), `slm_training`, `dual` |
| **`[slm]`** | `kernel_tree`: the tree parity and the chat eval build and boot in (empty in dual mode) |
| **`[hardware]`** | `research` (enables the Vendor Scout and Spec Reader), `fetch_hosts` (extra allowed hosts), `scout_count`, `reader_count` |

## Models

Qualify a model before spending a run on it:

```bash
.venv/bin/python scripts/model-probe.py claude-cli/claude-sonnet-5-5
```

Four checks: a tool call with the right name and arguments, a byte-exact file round trip, a
25,000-character prompt, and a second turn that moves on. Four early runs on an unqualified
model produced zero working lines.

With `claude-cli/…` as the model, a usage limit is waited out, or continued on a local
fallback model if one is configured and reachable (logged, and the run reported as
mixed-model).
