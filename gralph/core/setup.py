"""Project setup and initialization."""

import subprocess
from datetime import datetime
from pathlib import Path

from rich.panel import Panel

from gralph import GRALPH_DIR
from gralph.utils.console import console, prompt_input
from gralph.prompts import ARCHITECT_PROMPT, WORKER_PROMPT_TEMPLATE, CLARIFY_PROMPT
from gralph.core.prd import validate_prd
from gralph.core.claude import generate_prd, get_clarifying_questions


def is_python_stack(stack: str) -> bool:
    """Check if stack is Python-based."""
    python_keywords = ["python", "py", "flask", "django", "fastapi", "typer", "cli"]
    return any(kw in stack.lower() for kw in python_keywords)


def is_js_stack(stack: str) -> bool:
    """Check if stack is JavaScript/TypeScript-based."""
    js_keywords = ["javascript", "js", "typescript", "ts", "node", "react", "vue", "next", "bun"]
    return any(kw in stack.lower() for kw in js_keywords)


def init_package_manager(stack: str, project_dir: Path) -> None:
    """Initialize uv for Python or bun for JS projects, including test setup."""
    if is_python_stack(stack):
        if not (project_dir / "pyproject.toml").exists():
            result = subprocess.run(["uv", "init"], capture_output=True, text=True, cwd=project_dir)
            if result.returncode == 0:
                console.print("[dim]Initialized uv project[/dim]")
            else:
                console.print(f"[yellow]uv init failed: {result.stderr}[/yellow]")

        # Add pytest as dev dependency
        subprocess.run(["uv", "add", "--dev", "pytest"], capture_output=True, text=True, cwd=project_dir)
        console.print("[dim]Added pytest[/dim]")

        # Create tests directory with __init__.py
        tests_dir = project_dir / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "__init__.py").touch()
        console.print("[dim]Created tests/[/dim]")

    elif is_js_stack(stack):
        if not (project_dir / "package.json").exists():
            result = subprocess.run(["bun", "init", "-y"], capture_output=True, text=True, cwd=project_dir)
            if result.returncode == 0:
                console.print("[dim]Initialized bun project[/dim]")
            else:
                console.print(f"[yellow]bun init failed: {result.stderr}[/yellow]")

        # Create tests directory
        tests_dir = project_dir / "tests"
        tests_dir.mkdir(exist_ok=True)
        console.print("[dim]Created tests/[/dim]")


def setup_gitignore(project_dir: Path) -> None:
    """Ensure gralph internal files are in .gitignore."""
    gitignore = project_dir / ".gitignore"
    entries = [
        f"{GRALPH_DIR}/.ralph_error.txt",
        f"{GRALPH_DIR}/.ralph_state.json",
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
    console.print("\n[bold cyan]A few quick questions...[/bold cyan]")

    questions, error = get_clarifying_questions(goal, stack, CLARIFY_PROMPT)

    if error or not questions:
        console.print("[dim]Skipping clarifications.[/dim]")
        return ""

    answers = prompt_input(
        "Clarifying questions",
        hint=questions,
        required=False,
    )

    if not answers:
        return ""

    return f"Q&A:\n{questions}\n\nUser's answers:\n{answers}"


def core_setup(goal: str, stack: str, skip_clarify: bool = False, project_dir: Path | None = None) -> bool:
    """
    Core setup logic shared between init and bootstrap.

    Returns:
        True if setup succeeded, False otherwise.
    """
    if project_dir is None:
        project_dir = Path.cwd()

    gralph_dir = project_dir / GRALPH_DIR
    gralph_dir.mkdir(exist_ok=True)

    if not (project_dir / ".git").exists():
        subprocess.run(["git", "init"], capture_output=True, cwd=project_dir)
        console.print("[dim]Initialized git repository[/dim]")

    # Auto-init package manager based on stack
    init_package_manager(stack, project_dir)

    setup_gitignore(project_dir)

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
        console.print(f"[yellow]Edit {GRALPH_DIR}/PRD.md before running.[/yellow]")

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

    console.print(
        Panel.fit(
            f"[green]✅ Project gralph-ified![/green]\n\n"
            f"[bold]{GRALPH_DIR}/[/bold]\n"
            f"  ├── PRD.md        [dim]# Task list[/dim]\n"
            f"  ├── PROMPT.md     [dim]# Context for Claude[/dim]\n"
            f"  └── progress.txt  [dim]# Learnings log[/dim]\n\n"
            f"[bold]gralph run[/bold]      Start the loop\n"
            f"[bold]gralph status[/bold]   Show progress\n"
            f"[bold]gralph skip[/bold]     Skip current task\n"
            f"[bold]gralph edit[/bold]     Edit PRD",
            title="🍩 gralph",
        )
    )
    
    return True
