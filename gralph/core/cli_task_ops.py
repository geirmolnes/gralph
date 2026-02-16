"""Shared CLI operations for task, claim, and PRD status commands."""

import json
from pathlib import Path

import typer
from rich.table import Table

from gralph.utils.console import console
from gralph.core.claims import (
    claim_task,
    default_owner,
    get_active_claims,
    get_stale_claims,
    prune_expired_claims,
    release_claim,
)
from gralph.core.prd import (
    count_tasks,
    ensure_task_ids,
    find_task_by_id,
    fix_prd_format,
    get_ready_tasks,
    lint_prd,
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
    table.add_row("✅ Done", f"[green]{counts['completed']}[/green]")
    table.add_row("⏭️  Skip", f"[yellow]{counts['skipped']}[/yellow]")
    table.add_row("❌ Fail", f"[red]{counts['failed']}[/red]")
    table.add_row("⏳ Todo", f"{counts['pending']}")
    table.add_row("🔒 Claimed", f"{len(active_claims)}")
    if total > 0:
        table.add_row("📈 Progress", f"{(counts['completed'] / total) * 100:.0f}%")
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


def claim_by_id(gralph_dir: Path, task_id: str, owner: str | None, ttl_minutes: int) -> None:
    """Claim a specific pending task by id."""
    prd_path = gralph_dir / "PRD.md"
    prd_text = ensure_unique_ids(prd_path)
    task = find_task_by_id(prd_text, task_id)
    if not task:
        console.print(f"[red]Task id not found: {task_id}[/red]")
        raise typer.Exit(1)
    if task.status != " ":
        console.print(f"[yellow]Task {task_id} is not pending.[/yellow]")
        raise typer.Exit(1)

    claim_owner = owner or default_owner()
    ok, claimed_by = claim_task(
        gralph_dir,
        task_id=task_id,
        owner=claim_owner,
        lease_seconds=max(1, ttl_minutes) * 60,
    )
    if not ok:
        console.print(f"[yellow]Task {task_id} is already claimed by {claimed_by}.[/yellow]")
        raise typer.Exit(1)

    console.print(f"[green]Claimed {task_id} as {claim_owner} for {ttl_minutes}m.[/green]")


def release_by_id(gralph_dir: Path, task_id: str, owner: str | None, force: bool) -> None:
    """Release an active task claim."""
    release_owner = None if force else (owner or default_owner())
    ok = release_claim(
        gralph_dir,
        task_id=task_id,
        owner=release_owner,
        reason="manual_release",
    )
    if not ok:
        console.print(f"[yellow]No releasable claim found for {task_id}.[/yellow]")
        raise typer.Exit(1)
    console.print(f"[green]Released claim for {task_id}.[/green]")


def show_stale_claims(gralph_dir: Path, json_output: bool, prune: bool) -> None:
    """List stale claims and optionally prune them."""
    stale_claims = get_stale_claims(gralph_dir)
    if prune and stale_claims:
        prune_expired_claims(gralph_dir)

    if json_output:
        console.print_json(json.dumps(stale_claims))
        return

    if not stale_claims:
        console.print("[green]No stale claims.[/green]")
        return

    table = Table(title="Stale Claims")
    table.add_column("Task ID", style="cyan")
    table.add_column("Owner")
    table.add_column("Lease Until")
    for claim in stale_claims:
        table.add_row(
            claim.get("task_id", ""),
            claim.get("owner", ""),
            claim.get("lease_until", ""),
        )
    console.print(table)
    if prune:
        console.print("[dim]Pruned stale claims.[/dim]")


def lint_prd_file(prd_path: Path) -> None:
    """Run PRD lint checks and print diagnostics."""
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


def fix_prd_file(prd_path: Path) -> None:
    """Auto-fix PRD task formatting where possible."""
    original_text = prd_path.read_text()
    fixed_text, fixes = fix_prd_format(original_text)

    if fixes > 0:
        prd_path.write_text(fixed_text)
        console.print(
            f"[green]Applied {fixes} PRD formatting fix{'es' if fixes != 1 else ''}.[/green]"
        )
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


def show_tasks(gralph_dir: Path) -> None:
    """Print all tasks with status icons and colors."""
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
