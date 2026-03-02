"""CLI commands for gralph."""

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel

from gralph import GRALPH_DIR
from gralph.utils.console import console, show_version, prompt_input
from gralph.utils.paths import find_gralph_dir
from gralph.utils.deps import REQUIRED_TOOLS
from gralph.core.setup import core_setup, detect_stack
from gralph.core.loop import run_loop, pick_task, check_prd_format, ensure_task_ids_present
from gralph.core.cli_task_ops import (
    claim_by_id,
    ensure_unique_ids,
    fix_prd_file,
    lint_prd_file,
    release_by_id,
    show_ready,
    show_stale_claims,
    show_status,
    show_tasks,
)
from gralph.core.claims import (
    release_claim,
)
from gralph.core.prd import (
    mark_task,
    mark_task_by_id,
    parse_task_entries,
    reset_all_tasks,
)
from gralph.core.progress import append_learning

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


def _require_gralph_dir() -> Path:
    """Return gralph dir or exit if current directory is not initialized."""
    gralph_dir = find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)
    return gralph_dir


def _first_pending_task_id(prd_path: Path) -> str | None:
    """Return first pending task id after ensuring ids are present."""
    prd_text = ensure_unique_ids(prd_path)
    for entry in parse_task_entries(prd_text):
        if entry.status == " ":
            return entry.task_id
    return None


def _clear_runtime_state(gralph_dir: Path) -> None:
    """Clear cached loop state files after manual status updates."""
    (gralph_dir / ".ralph_error.txt").unlink(missing_ok=True)
    (gralph_dir / ".ralph_state.json").unlink(missing_ok=True)


def _mark_manual_status(
    task_id: Optional[str],
    status: str,
    status_label: str,
    release_reason: str,
) -> None:
    """Apply a manual task status update and synchronize claim state."""
    gralph_dir = _require_gralph_dir()
    prd_path = gralph_dir / "PRD.md"

    target_id = task_id or _first_pending_task_id(prd_path)
    task = mark_task_by_id(prd_path, task_id, status) if task_id else mark_task(prd_path, status)

    if not task:
        if task_id:
            console.print(f"[yellow]Task not pending or not found: {task_id}[/yellow]")
        else:
            console.print("[yellow]No pending tasks.[/yellow]")
        raise typer.Exit(0)

    console.print(f"{status_label} {task}")
    if target_id:
        release_claim(gralph_dir, target_id, owner=None, reason=release_reason)

    _clear_runtime_state(gralph_dir)


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
    owner: Optional[str] = typer.Option(None, "--owner", help="Claim owner identity for this run"),
):
    """Run the Ralph loop in Docker sandbox."""
    show_version()
    
    if not run_loop(max_iterations, completion_promise, model, push=push, owner=owner):
        raise typer.Exit(1)


@app.command()
def team(
    task_id: Optional[str] = typer.Argument(None, help="Task ID (picks next ready if omitted)"),
    model: str = typer.Option("sonnet", "--model", help="Claude model"),
    owner: Optional[str] = typer.Option(None, "--owner", help="Claim owner identity"),
):
    """Run a single task using an interactive Claude agent team."""
    import sys as _sys

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
    gralph_dir = _require_gralph_dir()

    if not check_prd_format(gralph_dir):
        raise typer.Exit(1)

    ensure_task_ids_present(gralph_dir)

    if not _sys.stdin.isatty():
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
def claim(
    task_id: str = typer.Argument(..., help="Task id to claim (for example: g-a1b2)"),
    owner: Optional[str] = typer.Option(None, "--owner", help="Claim owner identity"),
    ttl_minutes: int = typer.Option(90, "--ttl-minutes", help="Claim lease duration in minutes"),
):
    """Claim a specific pending task."""
    gralph_dir = _require_gralph_dir()
    claim_by_id(gralph_dir, task_id=task_id, owner=owner, ttl_minutes=ttl_minutes)


@app.command()
def release(
    task_id: str = typer.Argument(..., help="Task id to release"),
    owner: Optional[str] = typer.Option(None, "--owner", help="Owner identity (defaults to current user)"),
    force: bool = typer.Option(False, "--force", help="Release regardless of owner"),
):
    """Release an active task claim."""
    gralph_dir = _require_gralph_dir()
    release_by_id(gralph_dir, task_id=task_id, owner=owner, force=force)


@app.command()
def stale(
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON"),
    prune: bool = typer.Option(True, "--prune/--no-prune", help="Remove stale claims after listing"),
):
    """List stale (expired) claims."""
    gralph_dir = _require_gralph_dir()
    show_stale_claims(gralph_dir, json_output=json_output, prune=prune)


@app.command("lint-prd")
def lint_prd_command():
    """Check PRD task-line formatting."""
    lint_prd_file(_get_prd_path())


@app.command("fix-prd")
def fix_prd_command():
    """Auto-normalize common PRD task formatting issues."""
    fix_prd_file(_get_prd_path())


@app.command()
def skip(
    task_id: Optional[str] = typer.Argument(None, help="Optional task id to skip"),
):
    """Skip current task."""
    _mark_manual_status(
        task_id=task_id,
        status="~",
        status_label="[yellow]⏭️  Skipped:[/yellow]",
        release_reason="manual_skip",
    )


@app.command()
def done(
    task_id: Optional[str] = typer.Argument(None, help="Optional task id to mark done"),
):
    """Mark current task done manually."""
    _mark_manual_status(
        task_id=task_id,
        status="x",
        status_label="[green]✅ Done:[/green]",
        release_reason="manual_done",
    )


@app.command()
def tasks():
    """List all tasks with color-coded statuses."""
    gralph_dir = _require_gralph_dir()
    show_tasks(gralph_dir)


@app.command()
def fail(
    task_id: Optional[str] = typer.Argument(None, help="Optional task id to mark failed"),
):
    """Mark current task as failed."""
    _mark_manual_status(
        task_id=task_id,
        status="!",
        status_label="[red]❌ Failed:[/red]",
        release_reason="manual_fail",
    )


@app.command()
def edit(
    file: str = typer.Argument("prd", help="File to edit: prd, prompt, or progress"),
):
    """Open a planning file in editor."""
    gralph_dir = _require_gralph_dir()

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
    message: str = typer.Argument(..., help="Learning message to append"),
):
    """Add a numbered learning to the progress log."""
    gralph_dir = _require_gralph_dir()

    progress_file = gralph_dir / "progress.txt"
    append_learning(progress_file, message)

    console.print("[green]✏️  Logged.[/green]")


@app.command()
def reset():
    """Reset all tasks to pending."""
    gralph_dir = _require_gralph_dir()

    if not typer.confirm("Reset all tasks to pending?"):
        raise typer.Abort()

    reset_all_tasks(gralph_dir / "PRD.md")

    (gralph_dir / ".ralph_error.txt").unlink(missing_ok=True)
    (gralph_dir / ".ralph_state.json").unlink(missing_ok=True)
    (gralph_dir / "claims.json").unlink(missing_ok=True)
    (gralph_dir / "claims.lock").unlink(missing_ok=True)
    console.print("[green]All tasks reset.[/green]")


@app.command()
def progress():
    """View the progress log."""
    gralph_dir = _require_gralph_dir()

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
