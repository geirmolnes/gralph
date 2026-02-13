"""The Ralph loop - iterative task execution."""

import re
import sys
from pathlib import Path

from gralph import GRALPH_DIR
from gralph.utils.console import console, prompt_input
from gralph.utils.paths import find_gralph_dir
from gralph.prompts import LOOP_PROMPT_TEMPLATE, PUSH_INSTRUCTION, FOLLOW_UP_PROMPT
from gralph.core.claude import generate_follow_up_tasks
from gralph.core.prd import append_tasks, validate_prd
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


def _prompt_next_action(gralph_dir: Path) -> bool:
    """Prompt user for what to do after all tasks complete.

    Returns True if new tasks were added and the loop should continue.
    """
    console.print()
    console.rule("[bold green]All tasks complete[/bold green]")

    if not sys.stdin.isatty():
        return False

    response = prompt_input(
        "What next?",
        hint=(
            "1. Describe what to do next (AI will create new tasks)\n"
            "2. Leave blank and press Enter (AI will suggest next tasks)\n"
            "3. Type 'done' to finish"
        ),
        required=False,
    )

    if response.lower() in ("done", "quit", "exit", "q"):
        return False

    prd_path = gralph_dir / "PRD.md"
    prd_text = prd_path.read_text()
    stack = _extract_stack(prd_text)

    console.print("\n[bold green]🧠 Generating follow-up tasks...[/bold green]")

    new_tasks, error = generate_follow_up_tasks(
        prd_text, stack, FOLLOW_UP_PROMPT, user_instruction=response,
    )

    if error:
        console.print(f"[red]Failed to generate tasks: {error}[/red]")
        return False

    if not new_tasks or "|||" not in new_tasks:
        console.print("[yellow]No valid tasks generated.[/yellow]")
        return False

    is_valid, errors = validate_prd(new_tasks)
    if not is_valid:
        console.print("[yellow]Generated tasks have format issues:[/yellow]")
        for err in errors:
            console.print(f"  [dim]• {err}[/dim]")

    count = append_tasks(prd_path, new_tasks)
    if count == 0:
        console.print("[yellow]No tasks to add.[/yellow]")
        return False

    console.print(f"[green]Added {count} new task{'s' if count != 1 else ''} to PRD.[/green]")
    return True


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

                if _prompt_next_action(gralph_dir):
                    continue
                return True

        console.print()
        console.print(f"[yellow]⚠️  Reached max iterations ({max_iterations}).[/yellow]")
        console.print(f"Review {GRALPH_DIR}/PRD.md and run 'gralph run' again if needed.")
        return False

    except KeyboardInterrupt:
        console.print("\n[yellow]Loop paused. Run 'gralph run' to resume.[/yellow]")
        return False
