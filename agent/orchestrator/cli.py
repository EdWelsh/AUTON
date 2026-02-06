"""CLI entry point for AUTON."""

from __future__ import annotations

import asyncio
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
            console.print(f"  Then set your API key in {config_path} or export ANTHROPIC_API_KEY")
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


@cli.command()
@click.argument("goal")
@click.option("--workspace", "-w", default=None, help="Workspace directory (default: repo root)")
@click.option("--specs", "-s", default="kernel_spec", help="Kernel spec directory")
@click.pass_context
def run(ctx, goal: str, workspace: str | None, specs: str):
    """Run the agent orchestration loop to build toward a goal.

    GOAL is a high-level description of what to build, e.g.:
    "Build a minimal bootable x86_64 kernel that prints to serial console"
    """
    config = _load_config(ctx.obj["config_path"])

    # Fail fast if no API key is available
    api_key = config.get("llm", {}).get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]No API key found![/red]")
        console.print("[yellow]Set it via one of:[/yellow]")
        console.print("  1. Add api_key to [llm] section in config/auton.toml")
        console.print("  2. Export ANTHROPIC_API_KEY environment variable")
        raise SystemExit(1)

    # Default workspace is the repo root (parent of agent/)
    agent_dir = Path(__file__).resolve().parent.parent
    if workspace:
        workspace_path = Path(workspace).resolve()
    else:
        workspace_path = agent_dir.parent
    spec_path = (agent_dir / specs).resolve() if not Path(specs).is_absolute() else Path(specs).resolve()

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
    )

    result = asyncio.run(engine.run(goal))

    if result.get("success"):
        console.print("\n[bold green]Orchestration completed successfully![/bold green]")
    else:
        console.print(f"\n[bold red]Orchestration failed: {result.get('error', 'unknown')}[/bold red]")

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
