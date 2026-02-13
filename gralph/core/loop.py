"""The Ralph loop - iterative task execution."""

import re
import sys
from pathlib import Path

from gralph import GRALPH_DIR
from gralph.utils.console import console, prompt_input
from gralph.utils.paths import find_gralph_dir
from gralph.prompts import LOOP_PROMPT_TEMPLATE, PUSH_INSTRUCTION, FOLLOW_UP_PROMPT
from gralph.core.claude import generate_follow_up_tasks
from gralph.core.prd import append_tasks, count_tasks, validate_prd
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
) -> bool:
    """Run the Ralph loop with streaming output inside Docker sandbox."""
    gralph_dir = find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        console.print(
            "Run [bold]gralph init[/bold] or [bold]gralph bootstrap[/bold] first."
        )
        return False

    if not _ensure_pending_tasks(gralph_dir):
        return True

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
    console.print(f"[bold green]🍩 Running from:[/bold green] {project_dir.name}")
    console.print("[cyan]🐳 Docker sandbox[/cyan]")

    iteration = 0
    try:
        while iteration < max_iterations:
            iteration += 1
            console.print()
            console.rule(f"[bold cyan]Iteration {iteration} / {max_iterations}[/bold cyan]")
            console.print()

            push_instruction = PUSH_INSTRUCTION if push else ""
            prompt = LOOP_PROMPT_TEMPLATE.format(
                promise=completion_promise,
                push_instruction=push_instruction,
            )
            completed, output = stream_claude_docker(prompt, completion_promise, model, project_dir)

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
