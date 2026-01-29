"""The Ralph loop - iterative task execution."""

from pathlib import Path

from gralph.utils.console import console
from gralph.utils.paths import find_gralph_dir
from gralph.prompts import LOOP_PROMPT_TEMPLATE, PUSH_INSTRUCTION
from gralph.core.docker import (
    ensure_docker_available,
    ensure_image_exists,
    ensure_volume_exists,
    check_container_auth,
    fix_volume_permissions,
    stream_claude_docker,
)


def run_loop(
    max_iterations: int = 20,
    completion_promise: str = "<promise>COMPLETE</promise>",
    model: str = "sonnet",
    push: bool = False,
) -> bool:
    """
    Run the Ralph loop with streaming output inside Docker sandbox.
    
    Args:
        max_iterations: Maximum number of iterations
        completion_promise: Token that signals all tasks complete
        model: Claude model to use
        push: Push to remote after each commit
    
    Returns:
        True if all tasks completed, False if max iterations reached or interrupted.
    """
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

    try:
        for i in range(1, max_iterations + 1):
            console.print()
            console.rule(f"[bold cyan]Iteration {i} / {max_iterations}[/bold cyan]")
            console.print()
            
            push_instruction = PUSH_INSTRUCTION if push else ""
            prompt = LOOP_PROMPT_TEMPLATE.format(
                promise=completion_promise,
                push_instruction=push_instruction,
            )
            completed, output = stream_claude_docker(prompt, completion_promise, model, project_dir)
            
            if completed:
                console.print()
                console.print(f"[bold green]✅ PRD complete after {i} iterations![/bold green]")
                return True
        
        console.print()
        console.print(f"[yellow]⚠️  Reached max iterations ({max_iterations}).[/yellow]")
        console.print("Review gralph/PRD.md and run 'gralph run' again if needed.")
        return False
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Loop paused. Run 'gralph run' to resume.[/yellow]")
        return False
