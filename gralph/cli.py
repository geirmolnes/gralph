"""CLI commands for gralph."""

import json
import os
import shlex
import shutil
import subprocess
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
from gralph.core.setup import core_setup, detect_stack
from gralph.core.loop import run_loop
from gralph.core.prd import (
    count_tasks,
    fix_prd_format,
    lint_prd,
    mark_task,
    parse_all_tasks,
    parse_current_task,
    reset_all_tasks,
)

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


def _get_prd_path() -> Path:
    """Resolve PRD path or exit if not in a gralph project."""
    gralph_dir = find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    prd_path = gralph_dir / "PRD.md"
    if not prd_path.exists():
        console.print(f"[red]{GRALPH_DIR}/PRD.md not found.[/red]")
        raise typer.Exit(1)
    return prd_path


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

    path = path.resolve()
    path.mkdir()
    console.print(f"\n[dim]Created {name}/[/dim]")

    if not core_setup(resolved_goal, stack, skip_clarify=skip_clarify, project_dir=path):
        raise typer.Exit(1)

    console.print(f"\n[bold]Next:[/bold] cd {name}")


def _extract_suggested_goal(scan_output: str) -> str:
    """Parse the '## Suggested Goal' section from scan output."""
    lines = scan_output.split("\n")
    capture = False
    parts: list[str] = []
    for line in lines:
        if line.strip().lower().startswith("## suggested goal"):
            capture = True
            continue
        if capture:
            if line.startswith("## "):
                break
            parts.append(line)
    return "\n".join(parts).strip()


def _scan_and_suggest() -> str:
    """Scan codebase, show results, let user accept/modify suggested goal."""
    from gralph.core.claude import scan_codebase
    from gralph.prompts import SCAN_PROMPT

    console.print("\n[bold cyan]Scanning codebase...[/bold cyan]")
    scan_output, error = scan_codebase(SCAN_PROMPT)

    if error or not scan_output:
        console.print("[yellow]Scan failed, falling back to manual input.[/yellow]")
        return prompt_input(
            "What do you want to build?",
            hint="Describe your project. What's the core functionality?",
        )

    console.print(Panel(scan_output, title="Codebase Scan", border_style="cyan"))

    suggested = _extract_suggested_goal(scan_output)
    return prompt_input(
        "Goal",
        hint="Accept the suggestion or type your own.",
        default=suggested,
    )


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
            f"[yellow]Already gralph-ified. Use 'gralph run' or delete {GRALPH_DIR}/[/yellow]"
        )
        raise typer.Exit(1)

    # Scan mode: no explicit goal → scan codebase and suggest
    if not goal and not goal_file:
        resolved_goal = _scan_and_suggest()
        detected = detect_stack()
        if detected:
            stack = detected
            console.print(f"[dim]Detected stack: {stack}[/dim]")
        if not stack:
            stack = prompt_input(
                "Tech stack",
                hint="e.g. python, typescript, react, fastapi",
                default="python",
            )
        if not core_setup(resolved_goal, stack, skip_clarify=True):
            raise typer.Exit(1)
        return

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


@app.command("lint-prd")
def lint_prd_command():
    """Check PRD task-line formatting."""
    prd_path = _get_prd_path()
    prd_text = prd_path.read_text()
    errors = lint_prd(prd_text)

    if errors:
        console.print("[red]PRD format issues found:[/red]")
        for err in errors:
            console.print(f"  [dim]• {err}[/dim]")
        raise typer.Exit(1)

    total_tasks = sum(count_tasks(prd_text).values())
    if total_tasks == 0:
        console.print("[yellow]No task lines found in PRD.[/yellow]")
    else:
        console.print(f"[green]PRD format looks good ({total_tasks} tasks).[/green]")


@app.command("fix-prd")
def fix_prd_command():
    """Auto-normalize common PRD task formatting issues."""
    prd_path = _get_prd_path()
    original_text = prd_path.read_text()
    fixed_text, fixes = fix_prd_format(original_text)

    if fixes > 0:
        prd_path.write_text(fixed_text)
        console.print(f"[green]Applied {fixes} PRD formatting fix{'es' if fixes != 1 else ''}.[/green]")
    else:
        console.print("[dim]No auto-fixable PRD formatting issues found.[/dim]")

    remaining_errors = lint_prd(prd_path.read_text())
    if remaining_errors:
        console.print("[yellow]Remaining issues require manual edits:[/yellow]")
        for err in remaining_errors:
            console.print(f"  [dim]• {err}[/dim]")
        console.print("[yellow]Use 'gralph edit prd' to fix the remaining lines.[/yellow]")
        raise typer.Exit(1)

    total_tasks = sum(count_tasks(prd_path.read_text()).values())
    if total_tasks == 0:
        console.print("[yellow]PRD has no task lines yet.[/yellow]")
    else:
        console.print(f"[green]PRD format now valid ({total_tasks} tasks).[/green]")


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
def tasks():
    """List all tasks with color-coded statuses."""
    gralph_dir = find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    prd_text = (gralph_dir / "PRD.md").read_text()
    all_tasks = parse_all_tasks(prd_text)

    if not all_tasks:
        console.print("[yellow]No tasks found.[/yellow]")
        raise typer.Exit(0)

    style_map = {
        "x": ("green", "✅"),
        "~": ("yellow", "⏭️ "),
        "!": ("red", "❌"),
        " ": ("white", "⏳"),
    }
    for status, desc in all_tasks:
        color, icon = style_map.get(status, ("white", "  "))
        console.print(f"  {icon} [{color}]{desc}[/{color}]")


@app.command()
def fail():
    """Mark current task as failed."""
    gralph_dir = find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    prd_path = gralph_dir / "PRD.md"
    task = mark_task(prd_path, "!")

    if not task:
        console.print("[yellow]No pending tasks.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[red]❌ Failed:[/red] {task}")

    (gralph_dir / ".ralph_error.txt").unlink(missing_ok=True)
    (gralph_dir / ".ralph_state.json").unlink(missing_ok=True)


@app.command()
def edit(
    file: str = typer.Argument("prd", help="File to edit: prd, prompt, or progress"),
):
    """Open a planning file in editor."""
    gralph_dir = find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    file_map = {
        "prd": "PRD.md",
        "prompt": "PROMPT.md",
        "progress": "progress.txt",
    }
    filename = file_map.get(file.lower())
    if not filename:
        console.print(f"[red]Unknown file '{file}'. Choose: {', '.join(file_map)}[/red]")
        raise typer.Exit(1)

    target = gralph_dir / filename
    if not target.exists():
        console.print(f"[red]{filename} not found.[/red]")
        raise typer.Exit(1)

    editor = os.environ.get("EDITOR", "vim")
    editor_parts = shlex.split(editor)
    if not editor_parts:
        console.print("[red]EDITOR is set but empty.[/red]")
        raise typer.Exit(1)

    try:
        result = subprocess.run([*editor_parts, str(target)])
    except FileNotFoundError:
        console.print(f"[red]Editor command not found: {editor_parts[0]}[/red]")
        raise typer.Exit(1)

    if result.returncode != 0:
        raise typer.Exit(result.returncode)


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
def progress():
    """View the progress log."""
    gralph_dir = find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    progress_file = gralph_dir / "progress.txt"
    if not progress_file.exists():
        console.print("[yellow]No progress log yet.[/yellow]")
        raise typer.Exit(0)

    console.print(Panel(progress_file.read_text(), title="Progress Log", border_style="cyan"))


@app.command()
def rebuild():
    """Force rebuild of the Docker sandbox image."""
    from gralph.core.docker import ensure_docker_available, rebuild_image

    if not ensure_docker_available():
        console.print("[red]Docker is not available.[/red]")
        raise typer.Exit(1)

    if rebuild_image():
        console.print("[green]Docker image rebuilt.[/green]")
    else:
        console.print("[red]Rebuild failed.[/red]")
        raise typer.Exit(1)


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
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            console.print("  [red]✗[/red] Docker health check failed")
            console.print(f"    [dim]{exc}[/dim]")
            all_ok = False
        else:
            if result.returncode == 0:
                console.print("  [green]✓[/green] Docker daemon is running")
            else:
                console.print("  [red]✗[/red] Docker daemon not running")
                console.print("    [dim]Start Docker Desktop or run: sudo systemctl start docker[/dim]")
                all_ok = False

            # Check for gralph-sandbox image
            try:
                result = subprocess.run(
                    ["docker", "images", "-q", "gralph-sandbox"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                console.print("  [red]✗[/red] Failed to query Docker images")
                console.print(f"    [dim]{exc}[/dim]")
                all_ok = False
            else:
                if result.returncode != 0:
                    console.print("  [red]✗[/red] Failed to query Docker images")
                    all_ok = False
                elif result.stdout.strip():
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
