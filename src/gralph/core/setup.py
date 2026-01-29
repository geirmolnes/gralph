"""Project setup and initialization."""

import importlib.resources
import os
import subprocess
from datetime import datetime
from pathlib import Path

from rich.panel import Panel
from rich.prompt import Prompt

from gralph import GRALPH_DIR
from gralph.utils.console import console
from gralph.prompts import ARCHITECT_PROMPT, WORKER_PROMPT_TEMPLATE, CLARIFY_PROMPT
from gralph.core.prd import validate_prd
from gralph.core.claude import generate_prd, get_clarifying_questions


def load_ralph_sh() -> str:
    """Load ralph.sh template from package resources."""
    return importlib.resources.files("gralph.templates").joinpath("ralph.sh").read_text()


def setup_gitignore() -> None:
    """Ensure gralph internal files are in .gitignore."""
    gitignore = Path(".gitignore")
    entries = [
        "gralph/.ralph_error.txt",
        "gralph/.ralph_retries.txt",
        "gralph/.ralph_state.json",
    ]
    if not gitignore.exists():
        gitignore.write_text("# gralph internals\n" + "\n".join(entries) + "\n")
    else:
        content = gitignore.read_text()
        missing = [e for e in entries if e not in content]
        if missing:
            with open(gitignore, "a") as f:
                f.write("\n# gralph internals\n" + "\n".join(missing) + "\n")


def gather_clarifications(goal: str, stack: str) -> str:
    """Ask clarifying questions and gather answers."""
    console.print("[bold cyan]🤔 Let me ask a few questions to understand better...[/bold cyan]\n")
    
    questions, error = get_clarifying_questions(goal, stack, CLARIFY_PROMPT)
    
    if error or not questions:
        console.print("[yellow]Skipping clarifications...[/yellow]")
        return ""
    
    console.print(Panel(questions, title="Questions", border_style="cyan"))
    console.print()
    
    answers = Prompt.ask(
        "[bold]Your answers[/bold] (or press Enter to skip)",
        default="",
    )
    
    if not answers.strip():
        return ""
    
    return f"Q&A:\n{questions}\n\nUser's answers:\n{answers}"


def core_setup(goal: str, stack: str, skip_clarify: bool = False) -> bool:
    """
    Core setup logic shared between init and bootstrap.
    
    Returns:
        True if setup succeeded, False otherwise.
    """
    gralph_dir = Path(GRALPH_DIR)
    gralph_dir.mkdir(exist_ok=True)

    if not Path(".git").exists():
        subprocess.run(["git", "init"], capture_output=True)
        console.print("[dim]Initialized git repository[/dim]")

    setup_gitignore()

    # Gather clarifications unless skipped
    clarifications = ""
    if not skip_clarify:
        clarifications = gather_clarifications(goal, stack)
    
    console.print("\n[bold green]🧠 gralph is planning...[/bold green]")
    
    ai_prd, error = generate_prd(goal, stack, ARCHITECT_PROMPT, clarifications)
    
    if error:
        console.print(f"[red]Failed to generate PRD: {error}[/red]")
        return False

    if "|||" not in ai_prd:
        console.print("[red]Error: AI failed to format the PRD correctly.[/red]")
        console.print(Panel(ai_prd, title="Raw Output"))
        return False

    is_valid, errors = validate_prd(ai_prd)
    if not is_valid:
        console.print("[yellow]⚠️  PRD has format issues:[/yellow]")
        for err in errors:
            console.print(f"  [dim]• {err}[/dim]")
        console.print("[yellow]Edit gralph/PRD.md before running.[/yellow]")

    # Write PRD
    prd_content = f"# PRD: {goal}\n\nStack: {stack}\n\n{ai_prd}"
    (gralph_dir / "PRD.md").write_text(prd_content)

    # Write worker prompt
    prompt_content = WORKER_PROMPT_TEMPLATE.format(goal=goal, stack=stack)
    (gralph_dir / "PROMPT.md").write_text(prompt_content)

    # Initialize progress file
    progress_content = f"""# gralph Progress Log

## Codebase Patterns
- 

## Learnings

Project: {goal}
Stack: {stack}
Started: {datetime.now().isoformat()}

---
"""
    (gralph_dir / "progress.txt").write_text(progress_content)

    # Write ralph.sh script
    script_path = gralph_dir / "ralph.sh"
    script_path.write_text(load_ralph_sh())
    os.chmod(script_path, 0o755)

    console.print(
        Panel.fit(
            f"[green]✅ Project gralph-ified![/green]\n\n"
            f"[bold]gralph/[/bold]\n"
            f"  ├── PRD.md        [dim]# Task list[/dim]\n"
            f"  ├── PROMPT.md     [dim]# Context for Claude[/dim]\n"
            f"  ├── progress.txt  [dim]# Learnings log[/dim]\n"
            f"  └── ralph.sh      [dim]# Loop runner[/dim]\n\n"
            f"[bold]gralph run[/bold]      Start the loop\n"
            f"[bold]gralph status[/bold]   Show progress\n"
            f"[bold]gralph skip[/bold]     Skip current task\n"
            f"[bold]gralph edit[/bold]     Edit PRD",
            title="🍩 gralph",
        )
    )
    
    return True
