"""Shared CLI operations for task and PRD status commands."""

import json
from pathlib import Path

from rich.table import Table

from gralph.utils.console import console
from gralph.core.claims import get_active_claims
from gralph.core.prd import (
    count_tasks,
    ensure_task_ids,
    get_ready_tasks,
    parse_all_tasks,
    parse_current_task,
)


def ensure_unique_ids(prd_path: Path) -> str:
    """Ensure PRD tasks have stable unique IDs and return updated text."""
    prd_text = prd_path.read_text()
    updated_text, updated = ensure_task_ids(prd_text)
    if updated > 0:
        prd_path.write_text(updated_text)
        console.print(
            f"[dim]Updated IDs on {updated} task{'s' if updated != 1 else ''}.[/dim]"
        )
    return updated_text


def show_status(gralph_dir: Path) -> None:
    """Render current task and claim progress."""
    prd_text = (gralph_dir / "PRD.md").read_text()
    counts = count_tasks(prd_text)
    total = sum(counts.values())
    active_claims = get_active_claims(gralph_dir)

    table = Table(title="gralph Status")
    table.add_column("", style="bold")
    table.add_column("")
    table.add_row("Done", f"[green]{counts['completed']}[/green]")
    table.add_row("Skip", f"[yellow]{counts['skipped']}[/yellow]")
    table.add_row("Fail", f"[red]{counts['failed']}[/red]")
    table.add_row("Todo", f"{counts['pending']}")
    table.add_row("Claimed", f"{len(active_claims)}")
    if total > 0:
        table.add_row("Progress", f"{(counts['completed'] / total) * 100:.0f}%")
    console.print(table)

    current_task = parse_current_task(prd_text)
    if current_task:
        console.print(f"\n[bold]Next:[/bold] {current_task}")
    elif counts["pending"] == 0:
        console.print("\n[green]All tasks complete![/green]")

    state_file = gralph_dir / ".ralph_state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            console.print(
                f"\n[yellow]Paused:[/yellow] {state.get('current_task', 'unknown')}"
            )
            console.print(f"[dim]Since: {state.get('timestamp', 'unknown')}[/dim]")
        except json.JSONDecodeError:
            pass

    error_file = gralph_dir / ".ralph_error.txt"
    if error_file.exists():
        console.print(
            f"\n[yellow]Last error:[/yellow]\n[dim]{error_file.read_text()[:500]}[/dim]"
        )


def show_ready(gralph_dir: Path, json_output: bool) -> None:
    """Show ready tasks (dependencies satisfied and not claimed)."""
    prd_path = gralph_dir / "PRD.md"
    prd_text = ensure_unique_ids(prd_path)
    active_claims = get_active_claims(gralph_dir)
    unavailable = set(active_claims.keys())
    ready_tasks = get_ready_tasks(prd_text, unavailable_task_ids=unavailable)

    payload = [
        {
            "id": task.task_id,
            "description": task.description,
            "deps": list(task.deps),
            "verification": task.verification,
        }
        for task in ready_tasks
    ]

    if json_output:
        console.print_json(json.dumps(payload))
        return

    if not ready_tasks:
        pending = count_tasks(prd_text)["pending"]
        if pending == 0:
            console.print("[green]No pending tasks. PRD is complete.[/green]")
            return
        console.print(
            "[yellow]No tasks are currently ready (blocked by deps or claimed by another owner).[/yellow]"
        )
        if active_claims:
            console.print("[dim]Active claims:[/dim]")
            for task_id, claim in sorted(active_claims.items()):
                owner = claim.get("owner", "unknown")
                lease_until = claim.get("lease_until", "unknown")
                console.print(f"  [dim]• {task_id} ({owner}, lease until {lease_until})[/dim]")
        return

    table = Table(title="Ready Tasks")
    table.add_column("ID", style="cyan")
    table.add_column("Task")
    table.add_column("Deps", style="dim")
    for task in ready_tasks:
        table.add_row(
            task.task_id or "-",
            task.description,
            ", ".join(task.deps) if task.deps else "-",
        )
    console.print(table)


def show_tasks(gralph_dir: Path) -> None:
    """Print all tasks with status icons and colors."""
    prd_text = (gralph_dir / "PRD.md").read_text()
    all_tasks = parse_all_tasks(prd_text)

    if not all_tasks:
        console.print("[yellow]No tasks found.[/yellow]")
        return

    style_map = {
        "x": ("green", "done"),
        "~": ("yellow", "skip"),
        "!": ("red", "fail"),
        " ": ("white", "todo"),
    }
    for status, desc in all_tasks:
        color, icon = style_map.get(status, ("white", "    "))
        console.print(f"  {icon:4s} [{color}]{desc}[/{color}]")
