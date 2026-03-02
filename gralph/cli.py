"""CLI commands for gralph."""

import sys
from pathlib import Path
from typing import Optional

import typer

from gralph import GRALPH_DIR
from gralph.utils.console import console, show_version
from gralph.utils.paths import ensure_gralph_dir, find_gralph_dir
from gralph.core.loop import run_loop, pick_task, check_prd_format, ensure_task_ids_present
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
    task_id: Optional[str] = typer.Argument(None, help="Task ID (picks next ready if omitted)"),
    model: str = typer.Option("sonnet", "--model", help="Claude model"),
    owner: Optional[str] = typer.Option(None, "--owner", help="Claim owner identity"),
):
    """Run a single task using an interactive Claude agent team."""
    from gralph.core.claims import (
        DEFAULT_LEASE_SECONDS,
        claim_task as _claim_task,
        default_owner as _default_owner,
        release_claim as _release_claim,
    )
    from gralph.core.docker import (
        ensure_docker_available as _docker_ok,
        ensure_image_exists as _image_ok,
        ensure_volume_exists as _vol_ok,
        check_container_auth as _auth_ok,
        fix_volume_permissions as _fix_perms,
    )
    from gralph.core.prd import get_task_status_by_id as _status_by_id
    from gralph.core.team import run_team_task

    show_version()
    ensure_gralph_dir()
    gralph_dir = _require_gralph_dir()

    if not check_prd_format(gralph_dir):
        raise typer.Exit(1)

    ensure_task_ids_present(gralph_dir)

    if not sys.stdin.isatty():
        console.print("[red]Team mode requires an interactive terminal.[/red]")
        raise typer.Exit(1)

    # Docker checks
    for check, msg in [
        (_docker_ok, "Docker is not available."),
        (_image_ok, "Failed to setup Docker sandbox."),
        (_vol_ok, "Failed to create Docker volume."),
    ]:
        if not check():
            console.print(f"[red]{msg}[/red]")
            raise typer.Exit(1)

    _fix_perms()

    if not _auth_ok():
        console.print("[yellow]Claude not authenticated in container.[/yellow]")
        console.print("Run [bold]gralph auth[/bold] to authenticate.")
        raise typer.Exit(1)

    owner = owner or _default_owner()
    project_dir = gralph_dir.parent

    # Pick or locate task
    if task_id:
        from gralph.core.prd import find_task_by_id

        prd_text = (gralph_dir / "PRD.md").read_text()
        task = find_task_by_id(prd_text, task_id)
        if not task:
            console.print(f"[red]Task not found: {task_id}[/red]")
            raise typer.Exit(1)
    else:
        task, _ = pick_task(gralph_dir, owner)
        if task is None:
            console.print("[yellow]No ready tasks available.[/yellow]")
            raise typer.Exit(0)

    # Claim
    claimed, claimed_by = _claim_task(gralph_dir, task.task_id, owner=owner, lease_seconds=DEFAULT_LEASE_SECONDS)
    if not claimed:
        console.print(f"[yellow]Task {task.task_id} already claimed by {claimed_by}.[/yellow]")
        raise typer.Exit(1)

    console.print(f"[bold green]Team session[/bold green] for task [cyan]{task.task_id}[/cyan]")
    console.print(f"[dim]{task.description}[/dim]")
    console.print()

    success = run_team_task(task, gralph_dir, project_dir, model)

    # Post-session status check
    updated_prd = (gralph_dir / "PRD.md").read_text()
    task_status = _status_by_id(updated_prd, task.task_id)

    if task_status in {"x", "~", "!"}:
        _release_claim(gralph_dir, task.task_id, owner=owner, reason=f"task_{task_status}")
        console.print(f"[green]Task {task.task_id} marked [{task_status}].[/green]")
    else:
        _release_claim(gralph_dir, task.task_id, owner=owner, reason="session_ended")
        if success:
            console.print(f"[yellow]Session exited 0 but task {task.task_id} still pending.[/yellow]")
        else:
            console.print(f"[red]Session failed. Task {task.task_id} remains pending.[/red]")

    if not success:
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


if __name__ == "__main__":
    app()
