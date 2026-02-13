"""CLI commands for gralph."""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from gralph import __version__, GRALPH_DIR
from gralph.utils.console import console, show_version, prompt_input
from gralph.utils.paths import find_gralph_dir
from gralph.utils.deps import REQUIRED_TOOLS
from gralph.core.setup import core_setup
from gralph.core.loop import run_loop
from gralph.core.prd import count_tasks, parse_current_task, mark_task, reset_all_tasks

app = typer.Typer(
    name="gralph",
    help="Scaffold and run Ralph coding loops",
    invoke_without_command=True,
)


def _resolve_goal(goal: Optional[str], goal_file: Optional[Path]) -> str:
    """Resolve goal text from flags or interactive prompt."""
    # Load file context if provided
    file_context = ""
    if goal_file:
        if not goal_file.exists() or not goal_file.is_file():
            console.print(f"[red]Goal file not found: {goal_file}[/red]")
            raise typer.Exit(1)
        file_context = goal_file.read_text(encoding="utf-8").strip()
        if not file_context:
            console.print(f"[red]Goal file is empty: {goal_file}[/red]")
            raise typer.Exit(1)

    # If goal provided via flag, combine with file context
    if goal and goal.strip():
        if file_context:
            return f"{goal.strip()}\n\nAdditional context from {goal_file}:\n{file_context}"
        return goal.strip()

    # If only file context, use that
    if file_context:
        return file_context

    # Interactive prompt
    return prompt_input(
        "What do you want to build?",
        hint="Describe your project. What's the core functionality?",
    )


@app.callback()
def main(ctx: typer.Context):
    """gralph CLI entrypoint."""
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit(0)


@app.command()
def init(
    name: str = typer.Argument(..., help="Project directory name"),
    goal: Optional[str] = typer.Option(
        None, "--goal", "-g", help="What to build"
    ),
    stack: Optional[str] = typer.Option(
        None, "--stack", "-s", help="Tech stack"
    ),
    skip_clarify: bool = typer.Option(
        False, "--quick", "-q", help="Skip clarifying questions"
    ),
    goal_file: Optional[Path] = typer.Option(
        None, "--goal-file", help="Path to a long text/markdown file with project context"
    ),
):
    """Create a new project and initialize gralph."""
    path = Path(name)
    if path.exists():
        console.print(f"[red]Directory '{name}' already exists[/red]")
        raise typer.Exit(1)

    show_version()

    # Gather inputs before creating the directory (so Ctrl+C leaves nothing behind)
    resolved_goal = _resolve_goal(goal, goal_file)

    if not stack:
        stack = prompt_input(
            "Tech stack",
            hint="e.g. python, typescript, react, fastapi",
            default="python",
        )

    path.mkdir()
    os.chdir(path)
    console.print(f"\n[dim]Created {name}/[/dim]")

    if not core_setup(resolved_goal, stack, skip_clarify=skip_clarify):
        raise typer.Exit(1)

    console.print(f"\n[bold]Next:[/bold] cd {name}")


@app.command()
def bootstrap(
    goal: Optional[str] = typer.Option(
        None, "--goal", "-g", help="What to build"
    ),
    stack: Optional[str] = typer.Option(
        None, "--stack", "-s", help="Tech stack"
    ),
    skip_clarify: bool = typer.Option(
        False, "--quick", "-q", help="Skip clarifying questions"
    ),
    goal_file: Optional[Path] = typer.Option(
        None, "--goal-file", help="Path to a long text/markdown file with project context"
    ),
):
    """Initialize gralph in current directory."""
    show_version()

    if Path(GRALPH_DIR).exists() and (Path(GRALPH_DIR) / "PRD.md").exists():
        console.print(
            "[yellow]Already gralph-ified. Use 'gralph run' or delete gralph/[/yellow]"
        )
        raise typer.Exit(1)

    resolved_goal = _resolve_goal(goal, goal_file)

    if not stack:
        stack = prompt_input(
            "Tech stack",
            hint="e.g. python, typescript, react, fastapi",
            default="python",
        )

    if not core_setup(resolved_goal, stack, skip_clarify=skip_clarify):
        raise typer.Exit(1)


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
):
    """Run the Ralph loop in Docker sandbox."""
    show_version()
    
    if not run_loop(max_iterations, completion_promise, model, push=push):
        raise typer.Exit(1)


@app.command()
def status():
    """Show progress."""
    gralph_dir = find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    prd_text = (gralph_dir / "PRD.md").read_text()
    counts = count_tasks(prd_text)
    total = sum(counts.values())

    table = Table(title="gralph Status")
    table.add_column("", style="bold")
    table.add_column("")

    table.add_row("✅ Done", f"[green]{counts['completed']}[/green]")
    table.add_row("⏭️  Skip", f"[yellow]{counts['skipped']}[/yellow]")
    table.add_row("❌ Fail", f"[red]{counts['failed']}[/red]")
    table.add_row("⏳ Todo", f"{counts['pending']}")

    if total > 0:
        table.add_row("📈 Progress", f"{(counts['completed'] / total) * 100:.0f}%")

    console.print(table)

    current_task = parse_current_task(prd_text)
    if current_task:
        console.print(f"\n[bold]Next:[/bold] {current_task}")
    elif counts['pending'] == 0:
        console.print("\n[green]All tasks complete![/green]")

    # Show state if paused mid-task
    state_file = gralph_dir / ".ralph_state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            console.print(
                f"\n[yellow]⏸️  Paused:[/yellow] {state.get('current_task', 'unknown')}"
            )
            console.print(f"[dim]Since: {state.get('timestamp', 'unknown')}[/dim]")
        except json.JSONDecodeError:
            pass

    error_file = gralph_dir / ".ralph_error.txt"
    if error_file.exists():
        console.print(
            f"\n[yellow]Last error:[/yellow]\n[dim]{error_file.read_text()[:500]}[/dim]"
        )


@app.command()
def skip():
    """Skip current task."""
    gralph_dir = find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    prd_path = gralph_dir / "PRD.md"
    task = mark_task(prd_path, "~")
    
    if not task:
        console.print("[yellow]No pending tasks.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[yellow]⏭️  Skipped:[/yellow] {task}")

    (gralph_dir / ".ralph_error.txt").unlink(missing_ok=True)
    (gralph_dir / ".ralph_state.json").unlink(missing_ok=True)


@app.command()
def done():
    """Mark current task done manually."""
    gralph_dir = find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    prd_path = gralph_dir / "PRD.md"
    task = mark_task(prd_path, "x")
    
    if not task:
        console.print("[yellow]No pending tasks.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[green]✅ Done:[/green] {task}")

    (gralph_dir / ".ralph_error.txt").unlink(missing_ok=True)
    (gralph_dir / ".ralph_state.json").unlink(missing_ok=True)


@app.command()
def edit():
    """Open PRD in editor."""
    gralph_dir = find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    editor = os.environ.get("EDITOR", "vim")
    subprocess.run([editor, str(gralph_dir / "PRD.md")])


@app.command()
def log(
    message: str = typer.Argument(..., help="Message to add to progress log"),
):
    """Add a manual note to the progress log."""
    gralph_dir = find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    progress_file = gralph_dir / "progress.txt"
    with open(progress_file, "a") as f:
        f.write(f"\n## [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] NOTE\n")
        f.write(f"{message}\n")

    console.print("[green]✏️  Logged.[/green]")


@app.command()
def reset():
    """Reset all tasks to pending."""
    gralph_dir = find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    if not typer.confirm("Reset all tasks to pending?"):
        raise typer.Abort()

    reset_all_tasks(gralph_dir / "PRD.md")

    (gralph_dir / ".ralph_error.txt").unlink(missing_ok=True)
    (gralph_dir / ".ralph_state.json").unlink(missing_ok=True)
    console.print("[green]All tasks reset.[/green]")


@app.command()
def doctor():
    """Check system dependencies and configuration."""
    console.print("[bold]Checking dependencies...[/bold]\n")

    all_ok = True
    for tool, install_hint in REQUIRED_TOOLS.items():
        path = shutil.which(tool)
        if path:
            console.print(f"  [green]✓[/green] {tool}: {path}")
        else:
            console.print(f"  [red]✗[/red] {tool}: NOT FOUND")
            console.print(f"    [dim]{install_hint}[/dim]")
            all_ok = False

    # Check Docker daemon
    if shutil.which("docker"):
        console.print("\n[bold]Checking Docker daemon...[/bold]")
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            console.print("  [green]✓[/green] Docker daemon is running")
        else:
            console.print("  [red]✗[/red] Docker daemon not running")
            console.print("    [dim]Start Docker Desktop or run: sudo systemctl start docker[/dim]")
            all_ok = False
        
        # Check for gralph-sandbox image
        result = subprocess.run(
            ["docker", "images", "-q", "gralph-sandbox"],
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            console.print("  [green]✓[/green] gralph-sandbox image exists")
        else:
            console.print("  [yellow]![/yellow] gralph-sandbox image not built (will be built on first run)")

    if all_ok:
        console.print("\n[green]All dependencies satisfied![/green]")
    else:
        console.print(
            "\n[yellow]Some dependencies missing. Install them before running.[/yellow]"
        )
        raise typer.Exit(1)


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
