"""The Ralph loop - iterative task execution."""

import re
import sys
from pathlib import Path

from gralph import GRALPH_DIR
from gralph.utils.console import console, prompt_input
from gralph.utils.paths import find_gralph_dir
from gralph.prompts import (
    FOLLOW_UP_PROMPT,
    LOOP_PROMPT_TEMPLATE,
    PUSH_INSTRUCTION,
    TASK_SELECTION_PROMPT,
)
from gralph.core.claude import generate_follow_up_tasks, select_next_ready_task
from gralph.core.claims import (
    DEFAULT_LEASE_SECONDS,
    claim_task,
    default_owner,
    get_active_claims,
    release_claim,
)
from gralph.core.prd import (
    append_tasks,
    count_tasks,
    ensure_task_ids,
    get_ready_tasks,
    get_task_status_by_id,
    lint_prd,
    validate_prd,
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


def _extract_stack(prd_text: str) -> str:
    """Extract stack from PRD header."""
    match = re.search(r"^Stack:\s*(.+)$", prd_text, re.MULTILINE)
    return match.group(1).strip() if match else "python"


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


def _prompt_for_additional_tasks(gralph_dir: Path) -> bool:
    """Prompt for task generation when PRD has no pending tasks."""
    prd_path = gralph_dir / "PRD.md"

    choice = prompt_input(
        "No tasks available. What should gralph do next?",
        hint=(
            "1. Suggest tasks from recent PRD history and current codebase "
            "(you can refine after suggestions)\n"
            "2. Cancel"
        ),
        default="1",
        required=False,
    ).strip().lower()
    if choice in {"2", "cancel", "c", "q", "quit", "exit"}:
        console.print("[yellow]Cancelled. No new tasks added.[/yellow]")
        return False

    if choice not in {"", "1", "suggest", "s"}:
        console.print("[yellow]Please enter 1 or 2.[/yellow]")
        return _prompt_for_additional_tasks(gralph_dir)

    user_instruction = ""
    while True:
        if user_instruction:
            console.print("\n[bold green]🧠 Regenerating tasks with your refinement...[/bold green]")
        else:
            console.print("\n[bold green]🧠 Scanning recent tasks and codebase for suggestions...[/bold green]")

        prd_text = prd_path.read_text()
        stack = _extract_stack(prd_text)
        new_tasks, error = generate_follow_up_tasks(
            prd_text,
            stack,
            FOLLOW_UP_PROMPT,
            user_instruction=user_instruction,
        )

        if error:
            console.print(f"[red]Failed to generate tasks: {error}[/red]")
            continue
        if not new_tasks or "|||" not in new_tasks:
            console.print("[yellow]No valid tasks generated. Try again.[/yellow]")
            continue

        is_valid, errors = validate_prd(new_tasks)
        if not is_valid:
            console.print("[yellow]Generated tasks have format issues:[/yellow]")
            for err in errors:
                console.print(f"  [dim]• {err}[/dim]")

        console.print("\n[cyan]Proposed tasks:[/cyan]")
        console.print(new_tasks)

        action = prompt_input(
            "Add these tasks to PRD?",
            hint=(
                "Press Enter for yes, type a refinement to regenerate, or type "
                "'cancel' to stop."
            ),
            required=False,
        ).strip()
        lowered = action.lower()

        if lowered in {"cancel", "c", "q", "quit", "exit"}:
            console.print("[yellow]Cancelled. No new tasks added.[/yellow]")
            return False

        if lowered in {"", "y", "yes"}:
            count = append_tasks(prd_path, new_tasks)
            if count == 0:
                console.print("[yellow]No tasks to add.[/yellow]")
                user_instruction = ""
                continue

            console.print(f"[green]Added {count} new task{'s' if count != 1 else ''} to PRD.[/green]")
            return True

        if lowered in {"n", "no"}:
            user_instruction = ""
            continue

        user_instruction = action


def _ensure_pending_tasks(gralph_dir: Path) -> bool:
    """Ensure there is at least one pending PRD task before running the loop."""
    prd_text = (gralph_dir / "PRD.md").read_text()
    if count_tasks(prd_text)["pending"] > 0:
        return True

    console.print("\n[yellow]No tasks available in PRD.[/yellow]")
    if not sys.stdin.isatty():
        console.print("[yellow]Non-interactive session detected. Nothing to run.[/yellow]")
        return False

    return _prompt_for_additional_tasks(gralph_dir)


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
        "\n[yellow]Run [bold]gralph lint-prd[/bold] for details or "
        "[bold]gralph fix-prd[/bold] to normalize common formatting issues.[/yellow]"
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
) -> bool:
    """Run the Ralph loop with streaming output inside Docker sandbox."""
    gralph_dir = find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        console.print(
            "Run [bold]gralph init[/bold] or [bold]gralph bootstrap[/bold] first."
        )
        return False

    if not check_prd_format(gralph_dir):
        return False

    ensure_task_ids_present(gralph_dir)

    if not _ensure_pending_tasks(gralph_dir):
        return True

    ensure_task_ids_present(gralph_dir)

    start_counts = count_tasks((gralph_dir / "PRD.md").read_text())

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
    console.print(f"[bold green]🍩 Running from:[/bold green] {project_dir.name}")
    console.print("[cyan]🐳 Docker sandbox[/cyan]")
    console.print(f"[dim]Task owner: {owner}[/dim]")

    iteration = 0
    try:
        while iteration < max_iterations:
            pending_count = count_tasks((gralph_dir / "PRD.md").read_text())["pending"]
            if pending_count == 0:
                console.print()
                console.print(f"[bold green]✅ PRD complete after {iteration} iterations![/bold green]")
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
                    console.print("[red]Ready task is missing an id; run gralph fix-prd and retry.[/red]")
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
            completed, _ = stream_claude_docker(prompt, completion_promise, model, project_dir)

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
                # Renew lease if task remains pending for this owner.
                claim_task(
                    gralph_dir,
                    task.task_id,
                    owner=owner,
                    lease_seconds=DEFAULT_LEASE_SECONDS,
                )

            if completed:
                console.print()
                console.print(f"[bold green]✅ PRD complete after {iteration} iterations![/bold green]")
                end_counts = count_tasks((gralph_dir / "PRD.md").read_text())
                _print_run_summary(start_counts, end_counts, iteration)
                return True

        console.print()
        console.print(f"[yellow]⚠️  Reached max iterations ({max_iterations}).[/yellow]")
        console.print(f"Review {GRALPH_DIR}/PRD.md and run 'gralph run' again if needed.")
        end_counts = count_tasks((gralph_dir / "PRD.md").read_text())
        _print_run_summary(start_counts, end_counts, iteration)
        return False

    except KeyboardInterrupt:
        console.print("\n[yellow]Loop paused. Run 'gralph run' to resume.[/yellow]")
        end_counts = count_tasks((gralph_dir / "PRD.md").read_text())
        _print_run_summary(start_counts, end_counts, iteration)
        return False
