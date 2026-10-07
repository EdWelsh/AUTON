"""CLI entry point for AUTON."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Fix Windows encoding for Unicode output
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

console = Console(force_terminal=True)


def _load_config(config_path: Path) -> dict:
    """Load TOML configuration."""
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    if not config_path.exists():
        example = config_path.with_suffix(".toml.example")
        if example.exists():
            console.print(f"[red]Config not found: {config_path}[/red]")
            console.print(f"[yellow]Copy the example to get started:[/yellow]")
            console.print(f"  cp {example} {config_path}")
            console.print(f"  Then set your API keys in {config_path} or via environment variables")
        else:
            console.print(f"[red]Config not found: {config_path}[/red]")
        raise SystemExit(1)

    with open(config_path, "rb") as f:
        return tomllib.load(f)


@click.group()
@click.option("--config", "-c", default="config/auton.toml", help="Config file path")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx, config: str, verbose: bool):
    """AUTON - Agent orchestration for building an LLM hypervisor kernel."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = Path(config)



PROVIDER_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "azure": "AZURE_API_KEY",
}

# Providers that need no API key: a local Ollama, by either LiteLLM route.
# `ollama_chat` does native tool calling and is what a local run actually uses;
# it was missing from this list, and the first run on a qualified model died at
# startup with "No API key found for provider 'ollama_chat'".
KEYLESS_PROVIDERS = ("ollama", "ollama_chat", "claude-cli")  # claude-cli: the subscription


def has_api_key(provider: str, sources: dict) -> bool:
    """Whether `provider` can be called: a configured key, an env var, or no
    key needed at all."""
    return bool(
        provider in KEYLESS_PROVIDERS
        or provider in sources
        or os.environ.get(PROVIDER_ENV_VARS.get(provider, ""))
    )


# Exit statuses a caller can act on. 75 is EX_TEMPFAIL: the run paused at its
# time budget with its work committed, and `run --resume` continues it.
EXIT_PAUSED = 75
EXIT_RESUME_REFUSED = 2


@cli.command()
@click.argument("goal", required=False)
@click.option("--workspace", "-w", default=None, help="Workspace directory (default: repo root)")
@click.option("--specs", "-s", default="kernel_spec", help="Kernel spec directory")
@click.option("--resume", is_flag=True,
              help="Continue the paused run in this workspace instead of planning a new one")
@click.option("--subject", default=None, type=click.Path(exists=True, file_okay=False),
              help="An existing application to analyse; staged read-only at .auton/subject/")
@click.option("--manifest", "manifest_path", default=None,
              type=click.Path(exists=True, dir_okay=False),
              help="Build from a manifest: what the tree lacks becomes gated seed tasks")
@click.option("--probe", "probe_path", default=None,
              type=click.Path(exists=True, dir_okay=False),
              help="The operator's probe.yaml: what 'works' means (A10, A9)")
@click.option("--gate", "gates", multiple=True,
              help="A frozen gate suite the reviewer and tester may run (repeatable). "
                   "Also read from $AUTON_GATES as a JSON list.")
@click.pass_context
def run(ctx, goal: str | None, workspace: str | None, specs: str, resume: bool,
        subject: str | None, manifest_path: str | None, probe_path: str | None,
        gates: tuple[str, ...]):
    """Run the agent orchestration loop to build toward a goal.

    GOAL is a high-level description of what to build, e.g.:
    "Build a minimal bootable kernel that prints to serial console"

    With --resume, GOAL may be omitted: the saved run's goal is used.
    """
    if not goal and not resume and not manifest_path:
        raise click.UsageError("GOAL is required unless --resume or --manifest is given")
    config = _load_config(ctx.obj["config_path"])

    # Fail fast if no API key is available for the configured provider
    llm_config = config.get("llm", {})
    model = llm_config.get("model", "anthropic/claude-opus-4-6")
    provider = model.split("/")[0] if "/" in model else "anthropic"

    api_key_sources = dict(llm_config.get("api_keys", {}))
    # Backward compat: old single api_key field
    if "api_key" in llm_config:
        api_key_sources.setdefault("anthropic", llm_config["api_key"])

    if not has_api_key(provider, api_key_sources):
        env_var = PROVIDER_ENV_VARS.get(provider, f"{provider.upper()}_API_KEY")
        console.print(f"[red]No API key found for provider '{provider}'![/red]")
        console.print(f"[yellow]Configured model: {model}[/yellow]")
        console.print("[yellow]Set it via one of:[/yellow]")
        console.print(f"  1. Add '{provider}' key to [llm.api_keys] in config/auton.toml")
        console.print(f"  2. Export {env_var} environment variable")
        raise SystemExit(1)

    # Resolve the workspace. Agents and the build/test validators must all
    # target the same tree: the one holding the kernel Makefile + build/kernel.bin.
    # Priority: --workspace flag > [workspace].path in config > kernels/{arch}.
    agent_dir = Path(__file__).resolve().parent.parent
    repo_root = agent_dir.parent
    arch = config.get("kernel", {}).get("arch", "x86_64")
    if workspace:
        workspace_path = Path(workspace).resolve()
    else:
        configured = config.get("workspace", {}).get("path")
        if configured:
            # Config paths are written relative to the agent/ dir (e.g. "../kernels/x86_64").
            cfg_path = Path(configured)
            workspace_path = (
                cfg_path if cfg_path.is_absolute() else (agent_dir / cfg_path)
            ).resolve()
        else:
            workspace_path = (repo_root / "kernels" / arch).resolve()
    # The validators expect a Makefile + build/ at the workspace root.
    workspace_path.mkdir(parents=True, exist_ok=True)
    spec_path = (agent_dir / specs).resolve() if not Path(specs).is_absolute() else Path(specs).resolve()

    seed_tasks: list = []
    manifest_data: dict = {}
    if manifest_path and not resume:
        tools = agent_dir / "tools"
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        from intent_manifest import IntentError
        from manifest_goal import manifest_from_json, plan
        try:
            handoff = plan(manifest_from_json(Path(manifest_path).read_text()), workspace_path)
        except IntentError as exc:
            console.print(f"[red]Refusing the manifest: {exc}[/red]")
            raise SystemExit(2)
        goal = goal or handoff.goal
        seed_tasks = handoff.seed_tasks
        import json as _json
        manifest_data = _json.loads(Path(manifest_path).read_text())

    if resume and not goal:
        state_path = workspace_path / ".auton" / "state.json"
        if not state_path.exists():
            console.print(f"[red]Refusing to resume: no saved run at {state_path}[/red]")
            raise SystemExit(EXIT_RESUME_REFUSED)
        from orchestrator.core.state import OrchestratorState
        goal = OrchestratorState.load(state_path).goal

    console.print(f"\n[bold green]AUTON Orchestration Engine[/bold green]")
    console.print(f"Goal: {goal}")
    console.print(f"Workspace: {workspace_path}")
    console.print(f"Specs: {spec_path}")
    console.print()

    from orchestrator.core.engine import OrchestrationEngine

    engine = OrchestrationEngine(
        workspace_path=workspace_path,
        kernel_spec_path=spec_path,
        config=config,
        subject_path=Path(subject).resolve() if subject else None,
        seed_tasks=seed_tasks,
        manifest=manifest_data,
        probe_path=Path(probe_path) if probe_path else None,
        gate_commands=list(gates) or json.loads(os.environ.get("AUTON_GATES") or "[]"),
    )

    result = asyncio.run(engine.run(goal, resume=resume))

    if refusal := result.get("resume_refused"):
        console.print(f"\n[bold red]Refusing to resume: {refusal}[/bold red]")
        raise SystemExit(EXIT_RESUME_REFUSED)

    if result.get("paused"):
        # The wording is what orchestrate-native.sh greps for.
        console.print(f"\n[bold yellow]Orchestration paused at iteration "
                      f"{result.get('iterations', 0)}; work in flight is committed. "
                      f"Continue with: run --resume[/bold yellow]")
        _print_progress(result)
        raise SystemExit(EXIT_PAUSED)

    if result.get("success"):
        console.print("\n[bold green]Orchestration completed successfully![/bold green]")
    else:
        console.print(f"\n[bold red]Orchestration failed: {result.get('error', 'unknown')}[/bold red]")

    _print_progress(result)


def _print_progress(result: dict) -> None:
    console.print(f"Total cost: ${result.get('total_cost_usd', 0):.2f}")
    console.print(f"Iterations: {result.get('iterations', 0)}")

    if progress := result.get("progress"):
        table = Table(title="Task Progress")
        table.add_column("State", style="cyan")
        table.add_column("Count", style="magenta")
        for state, count in sorted(progress.items()):
            table.add_row(state, str(count))
        console.print(table)


@cli.command()
@click.option("--workspace", "-w", default="workspace", help="Workspace directory")
def status(workspace: str):
    """Show the current status of an orchestration run."""
    workspace_path = Path(workspace).resolve()
    state_path = workspace_path / ".auton" / "state.json"

    if not state_path.exists():
        console.print("[yellow]No active run found.[/yellow]")
        return

    from orchestrator.core.state import OrchestratorState
    state = OrchestratorState.load(state_path)

    table = Table(title=f"AUTON Run {state.run_id}")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Goal", state.goal)
    table.add_row("Phase", state.phase)
    table.add_row("Iteration", str(state.iteration))
    table.add_row("Tasks Created", str(state.tasks_created))
    table.add_row("Tasks Completed", str(state.tasks_completed))
    table.add_row("Tasks Failed", str(state.tasks_failed))
    table.add_row("Total Cost", f"${state.total_cost_usd:.2f}")
    console.print(table)

    if state.errors:
        console.print(f"\n[red]Last {min(5, len(state.errors))} errors:[/red]")
        for err in state.errors[-5:]:
            console.print(f"  [{err['agent_id']}] {err['error'][:100]}")


@cli.command()
@click.option("--workspace", "-w", default="workspace", help="Workspace directory")
def agents(workspace: str):
    """List registered agents and their status."""
    workspace_path = Path(workspace).resolve()
    state_path = workspace_path / ".auton" / "state.json"

    if not state_path.exists():
        console.print("[yellow]No active run found.[/yellow]")
        return

    from orchestrator.core.state import OrchestratorState
    state = OrchestratorState.load(state_path)

    table = Table(title="Agent Status")
    table.add_column("Agent ID", style="cyan")
    table.add_column("State", style="green")

    for agent_id, agent_state in state.agent_states.items():
        table.add_row(agent_id, agent_state)

    console.print(table)


@cli.command()
@click.option("--workspace", "-w", default="workspace", help="Workspace directory")
def tasks(workspace: str):
    """List all tasks and their status."""
    workspace_path = Path(workspace).resolve()

    from orchestrator.comms.diff_protocol import TaskMetadata
    all_tasks = TaskMetadata.load_all(workspace_path)

    if not all_tasks:
        console.print("[yellow]No tasks found.[/yellow]")
        return

    table = Table(title="Tasks")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Subsystem", style="blue")
    table.add_column("Status", style="green")
    table.add_column("Agent", style="yellow")

    for task in all_tasks:
        status_style = {
            "pending": "dim",
            "in_progress": "yellow",
            "review": "blue",
            "approved": "green",
            "rejected": "red",
            "merged": "bold green",
            "blocked": "red",
        }.get(task.status.value, "white")

        table.add_row(
            task.task_id,
            task.title[:50],
            task.subsystem,
            f"[{status_style}]{task.status.value}[/{status_style}]",
            task.agent_id or "-",
        )

    console.print(table)


def main():
    cli()


if __name__ == "__main__":  # pragma: no cover
    # Without this, `python -m orchestrator.cli ...` exits 0 having done
    # nothing — the module imports, defines the group, and returns.
    main()
