"""CLI commands for gralph."""

from pathlib import Path
from typing import Optional

import typer

from gralph import GRALPH_DIR
from gralph.utils.console import console, show_version
from gralph.utils.paths import ensure_gralph_dir, find_gralph_dir
from gralph.core.loop import run_loop
from gralph.core.cli_task_ops import (
    show_ready,
    show_status,
    show_tasks,
)

app = typer.Typer(
    name="gralph",
    help="Run Ralph coding loops",
    invoke_without_command=True,
)


def _require_gralph_dir() -> Path:
    """Return gralph dir or exit if current directory is not initialized."""
    gralph_dir = find_gralph_dir()
    if not gralph_dir:
        console.print(f"[red]No {GRALPH_DIR}/PRD.md found.[/red]")
        raise typer.Exit(1)
    return gralph_dir


@app.callback()
def main(ctx: typer.Context):
    """gralph CLI entrypoint."""
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit(0)


@app.command()
def run(
    max_iterations: int = typer.Argument(20, help="Max iterations"),
    completion_promise: str = typer.Option(
        "<promise>COMPLETE</promise>",
        "--promise",
        "-p",
        help="Completion promise token",
    ),
    model: str = typer.Option("sonnet", "--model", help="Claude model to use"),
    push: bool = typer.Option(False, "--push", help="Push to remote after each commit"),
    owner: Optional[str] = typer.Option(None, "--owner", help="Claim owner identity for this run"),
):
    """Run the Ralph loop in Docker sandbox."""
    show_version()
    ensure_gralph_dir()

    if not run_loop(max_iterations, completion_promise, model, push=push, owner=owner):
        raise typer.Exit(1)


@app.command()
def team(
    max_iterations: int = typer.Argument(20, help="Max iterations"),
    completion_promise: str = typer.Option(
        "<promise>COMPLETE</promise>",
        "--promise",
        "-p",
        help="Completion promise token",
    ),
    model: str = typer.Option("sonnet", "--model", help="Claude model to use"),
    push: bool = typer.Option(False, "--push", help="Push to remote after each commit"),
    owner: Optional[str] = typer.Option(None, "--owner", help="Claim owner identity for this run"),
):
    """Run the Ralph loop with agent teams enabled."""
    show_version()
    ensure_gralph_dir()

    if not run_loop(max_iterations, completion_promise, model, push=push, owner=owner, agent_teams=True):
        raise typer.Exit(1)


@app.command()
def status():
    """Show progress."""
    gralph_dir = _require_gralph_dir()
    show_status(gralph_dir)


@app.command()
def ready(
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON"),
):
    """Show ready-to-run tasks (deps satisfied and not actively claimed)."""
    gralph_dir = _require_gralph_dir()
    show_ready(gralph_dir, json_output=json_output)


@app.command()
def tasks():
    """List all tasks with color-coded statuses."""
    gralph_dir = _require_gralph_dir()
    show_tasks(gralph_dir)


@app.command()
def auth():
    """Authenticate Claude inside Docker container."""
    from gralph.core.docker import (
        ensure_docker_available,
        ensure_image_exists,
        ensure_volume_exists,
        authenticate_container,
    )

    if not ensure_docker_available():
        console.print("[red]Docker is not available.[/red]")
        raise typer.Exit(1)

    if not ensure_image_exists():
        raise typer.Exit(1)

    if not ensure_volume_exists():
        raise typer.Exit(1)

    if authenticate_container():
        console.print("\n[green]Authentication successful![/green]")
    else:
        console.print("\n[red]Authentication failed.[/red]")
        raise typer.Exit(1)


@app.command()
def version():
    """Show gralph version."""
    show_version()


if __name__ == "__main__":
    app()
