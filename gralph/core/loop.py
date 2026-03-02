"""The Ralph loop - iterative task execution."""

import sys
from pathlib import Path

from gralph import GRALPH_DIR
from gralph.utils.console import console
from gralph.utils.paths import find_gralph_dir
from gralph.prompts import (
    LOOP_PROMPT_TEMPLATE,
    PUSH_INSTRUCTION,
    TASK_SELECTION_PROMPT,
)
from gralph.core.claude import select_next_ready_task
from gralph.core.claims import (
    DEFAULT_LEASE_SECONDS,
    claim_task,
    default_owner,
    get_active_claims,
    release_claim,
)
from gralph.core.prd import (
    count_tasks,
    ensure_task_ids,
    get_ready_tasks,
    get_task_status_by_id,
    lint_prd,
)
from gralph.core.progress import build_memory_snapshot
from gralph.core.docker import (
    ensure_docker_available,
    ensure_image_exists,
    ensure_volume_exists,
    check_container_auth,
    fix_volume_permissions,
    stream_claude_docker,
)


def ensure_task_ids_present(gralph_dir: Path) -> None:
    """Guarantee all task lines have stable unique task IDs."""
    prd_path = gralph_dir / "PRD.md"
    prd_text = prd_path.read_text()
    updated_text, updated = ensure_task_ids(prd_text)
    if updated > 0:
        prd_path.write_text(updated_text)
        console.print(
            f"[dim]Updated IDs on {updated} task{'s' if updated != 1 else ''}.[/dim]"
        )


def _build_task_locked_prompt(
    task_id: str,
    description: str,
    verification: str,
    completion_promise: str,
    push: bool,
    memory_snapshot: str,
) -> str:
    """Build loop prompt locked to one model-selected ready task."""
    push_instruction = PUSH_INSTRUCTION if push else ""
    scheduler_block = (
        "SCHEDULER-SELECTED TASK (MANDATORY):\n"
        f"- Task ID: {task_id}\n"
        f"- Description: {description}\n"
        f"- Verification command: {verification}\n\n"
        "You MUST work only on this task ID this iteration.\n"
        "Do not start or complete any other task.\n"
        "If verification passes, update this exact task in PRD.md.\n\n"
    )
    return scheduler_block + LOOP_PROMPT_TEMPLATE.format(
        memory_snapshot=memory_snapshot,
        promise=completion_promise,
        push_instruction=push_instruction,
    )


def pick_task(
    gralph_dir: Path,
    owner: str,
) -> tuple[object | None, str]:
    """Pick one ready task (model-ranked when multiple candidates)."""
    prd_text = (gralph_dir / "PRD.md").read_text()
    claims = get_active_claims(gralph_dir)
    unavailable = {
        task_id
        for task_id, claim in claims.items()
        if claim.get("owner") != owner
    }
    ready_tasks = get_ready_tasks(prd_text, unavailable_task_ids=unavailable)
    if not ready_tasks:
        return None, prd_text

    if len(ready_tasks) == 1:
        return ready_tasks[0], prd_text

    candidates = [
        {
            "task_id": task.task_id or "",
            "description": task.description,
            "verification": task.verification,
            "deps": ", ".join(task.deps),
        }
        for task in ready_tasks
    ]
    selected_id, error = select_next_ready_task(prd_text, candidates, TASK_SELECTION_PROMPT)
    if error:
        console.print(f"[dim]Task prioritization fallback: {error}[/dim]")
        return ready_tasks[0], prd_text

    for task in ready_tasks:
        if task.task_id == selected_id:
            return task, prd_text

    console.print("[dim]Task prioritization fallback: selected id not in ready set.[/dim]")
    return ready_tasks[0], prd_text


def check_prd_format(gralph_dir: Path) -> bool:
    """Validate PRD formatting before entering the execution loop."""
    prd_text = (gralph_dir / "PRD.md").read_text()
    errors = lint_prd(prd_text)
    if not errors:
        return True

    console.print("\n[red]PRD format issues detected:[/red]")
    for err in errors[:20]:
        console.print(f"  [dim]• {err}[/dim]")
    if len(errors) > 20:
        console.print(f"  [dim]• ...and {len(errors) - 20} more[/dim]")

    console.print(
        "\n[yellow]Fix PRD task formatting and try again.[/yellow]"
    )
    return False


def _print_run_summary(
    start_counts: dict[str, int],
    end_counts: dict[str, int],
    iterations: int,
) -> None:
    """Print a short summary for the just-finished run."""
    done_delta = end_counts["completed"] - start_counts["completed"]
    skipped_delta = end_counts["skipped"] - start_counts["skipped"]
    failed_delta = end_counts["failed"] - start_counts["failed"]

    console.print()
    console.rule("[bold]Run Summary[/bold]")
    console.print(f"Iterations run: {iterations}")
    console.print(f"Completed this run: {done_delta:+d}")
    console.print(f"Skipped this run: {skipped_delta:+d}")
    console.print(f"Failed this run: {failed_delta:+d}")
    console.print(
        f"Current totals -> done: {end_counts['completed']}, "
        f"skipped: {end_counts['skipped']}, failed: {end_counts['failed']}, "
        f"pending: {end_counts['pending']}"
    )


def run_loop(
    max_iterations: int = 20,
    completion_promise: str = "<promise>COMPLETE</promise>",
    model: str = "sonnet",
    push: bool = False,
    owner: str | None = None,
    agent_teams: bool = False,
) -> bool:
    """Run the Ralph loop with streaming output inside Docker sandbox."""
    gralph_dir = find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project. No gralph/PRD.md found.[/red]")
        return False

    if not check_prd_format(gralph_dir):
        return False

    ensure_task_ids_present(gralph_dir)

    # No pending tasks → nothing to do
    prd_text = (gralph_dir / "PRD.md").read_text()
    if count_tasks(prd_text)["pending"] == 0:
        console.print("[green]No pending tasks. PRD is complete.[/green]")
        return True

    start_counts = count_tasks(prd_text)

    # Setup Docker sandbox
    if not ensure_docker_available():
        console.print("[red]Docker is not available. Install Docker to run gralph.[/red]")
        return False

    if not ensure_image_exists():
        console.print("[red]Failed to setup Docker sandbox.[/red]")
        return False

    if not ensure_volume_exists():
        console.print("[red]Failed to create Docker volume.[/red]")
        return False

    fix_volume_permissions()

    if not check_container_auth():
        console.print("[yellow]Claude not authenticated in container.[/yellow]")
        console.print("Run [bold]gralph auth[/bold] to authenticate.")
        return False

    project_dir = gralph_dir.parent
    owner = owner or default_owner()
    console.print(f"[bold green]Running from:[/bold green] {project_dir.name}")
    console.print(f"[dim]Task owner: {owner}[/dim]")

    iteration = 0
    try:
        while iteration < max_iterations:
            pending_count = count_tasks((gralph_dir / "PRD.md").read_text())["pending"]
            if pending_count == 0:
                console.print()
                console.print(f"[bold green]PRD complete after {iteration} iterations![/bold green]")
                end_counts = count_tasks((gralph_dir / "PRD.md").read_text())
                _print_run_summary(start_counts, end_counts, iteration)
                return True

            task, prd_text = pick_task(gralph_dir, owner)
            if task is None:
                console.print(
                    "[yellow]No ready tasks are currently runnable (blocked by dependencies or claimed by another owner).[/yellow]"
                )
                end_counts = count_tasks(prd_text)
                _print_run_summary(start_counts, end_counts, iteration)
                return False

            if not task.task_id:
                ensure_task_ids_present(gralph_dir)
                task, prd_text = pick_task(gralph_dir, owner)
                if task is None or not task.task_id:
                    console.print("[red]Ready task is missing an id.[/red]")
                    return False

            claimed, claimed_by = claim_task(
                gralph_dir,
                task.task_id,
                owner=owner,
                lease_seconds=DEFAULT_LEASE_SECONDS,
            )
            if not claimed:
                console.print(
                    f"[yellow]Task {task.task_id} claimed by {claimed_by}; retrying selection.[/yellow]"
                )
                continue

            iteration += 1
            console.print()
            console.rule(f"[bold cyan]Iteration {iteration} / {max_iterations}[/bold cyan]")
            console.print(
                f"[bold]Task:[/bold] [cyan]{task.task_id}[/cyan] - {task.description}"
            )
            console.print()

            prompt = _build_task_locked_prompt(
                task_id=task.task_id,
                description=task.description,
                verification=task.verification,
                completion_promise=completion_promise,
                push=push,
                memory_snapshot=build_memory_snapshot(gralph_dir / "progress.txt"),
            )
            completed, _ = stream_claude_docker(prompt, completion_promise, model, project_dir, agent_teams=agent_teams)

            updated_prd = (gralph_dir / "PRD.md").read_text()
            task_status = get_task_status_by_id(updated_prd, task.task_id)
            if task_status in {"x", "~", "!"}:
                release_claim(
                    gralph_dir,
                    task.task_id,
                    owner=owner,
                    reason=f"task_{task_status}",
                )
            else:
                claim_task(
                    gralph_dir,
                    task.task_id,
                    owner=owner,
                    lease_seconds=DEFAULT_LEASE_SECONDS,
                )

            if completed:
                console.print()
                console.print(f"[bold green]PRD complete after {iteration} iterations![/bold green]")
                end_counts = count_tasks((gralph_dir / "PRD.md").read_text())
                _print_run_summary(start_counts, end_counts, iteration)
                return True

        console.print()
        console.print(f"[yellow]Reached max iterations ({max_iterations}).[/yellow]")
        console.print(f"Review {GRALPH_DIR}/PRD.md and run 'gralph run' again if needed.")
        end_counts = count_tasks((gralph_dir / "PRD.md").read_text())
        _print_run_summary(start_counts, end_counts, iteration)
        return False

    except KeyboardInterrupt:
        console.print("\n[yellow]Loop paused. Run 'gralph run' to resume.[/yellow]")
        end_counts = count_tasks((gralph_dir / "PRD.md").read_text())
        _print_run_summary(start_counts, end_counts, iteration)
        return False
