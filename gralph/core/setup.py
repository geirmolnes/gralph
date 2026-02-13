"""Project setup and initialization."""

import re
import subprocess
from datetime import datetime
from pathlib import Path

from rich.panel import Panel

from gralph import GRALPH_DIR
from gralph.utils.console import console, prompt_input
from gralph.prompts import ARCHITECT_PROMPT, WORKER_PROMPT_TEMPLATE, CLARIFY_PROMPT
from gralph.core.prd import validate_prd
from gralph.core.claude import generate_prd, get_clarifying_questions


PYTHON_STACK_KEYWORDS = {"python", "py", "flask", "django", "fastapi", "typer"}
JS_STACK_KEYWORDS = {"javascript", "js", "typescript", "ts", "node", "react", "vue", "next", "bun"}


def detect_stack(project_dir: Path | None = None) -> str | None:
    """Auto-detect stack from project files. Returns None if undetectable."""
    d = project_dir or Path.cwd()
    if (d / "pyproject.toml").exists():
        return "python"
    has_pkg = (d / "package.json").exists()
    if has_pkg and (d / "tsconfig.json").exists():
        return "typescript"
    if has_pkg:
        return "javascript"
    return None


def _tokenize_stack(stack: str) -> set[str]:
    """Tokenize free-form stack text into lowercase words."""
    return {t for t in re.split(r"[^a-z0-9+]+", stack.lower()) if t}


def _run_command(
    args: list[str],
    project_dir: Path,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str] | None:
    """Run a local command and return None on common process errors."""
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=project_dir,
            timeout=timeout,
        )
    except FileNotFoundError:
        console.print(f"[yellow]Command not found: {args[0]}[/yellow]")
    except subprocess.TimeoutExpired:
        console.print(f"[yellow]Command timed out: {' '.join(args)}[/yellow]")
    return None


def is_python_stack(stack: str) -> bool:
    """Check if stack is Python-based."""
    return bool(_tokenize_stack(stack) & PYTHON_STACK_KEYWORDS)


def is_js_stack(stack: str) -> bool:
    """Check if stack is JavaScript/TypeScript-based."""
    return bool(_tokenize_stack(stack) & JS_STACK_KEYWORDS)


def init_package_manager(stack: str, project_dir: Path) -> None:
    """Initialize uv for Python or bun for JS projects, including test setup."""
    detected = detect_stack(project_dir)
    if detected == "python":
        stack_family = "python"
    elif detected in {"javascript", "typescript"}:
        stack_family = "javascript"
    else:
        python_like = is_python_stack(stack)
        js_like = is_js_stack(stack)
        if python_like and not js_like:
            stack_family = "python"
        elif js_like and not python_like:
            stack_family = "javascript"
        elif python_like and js_like:
            console.print(
                "[yellow]Stack looks mixed between Python and JS; skipping package manager initialization.[/yellow]"
            )
            return
        else:
            console.print(
                "[yellow]Could not detect package manager from stack; skipping package manager initialization.[/yellow]"
            )
            return

    if stack_family == "python":
        if not (project_dir / "pyproject.toml").exists():
            result = _run_command(["uv", "init"], project_dir)
            if result and result.returncode == 0:
                console.print("[dim]Initialized uv project[/dim]")
            elif result:
                console.print(f"[yellow]uv init failed: {result.stderr.strip()}[/yellow]")

        result = _run_command(["uv", "add", "--dev", "pytest"], project_dir)
        if result and result.returncode == 0:
            console.print("[dim]Added pytest[/dim]")
        elif result:
            console.print(f"[yellow]uv add --dev pytest failed: {result.stderr.strip()}[/yellow]")

        tests_dir = project_dir / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "__init__.py").touch()
        console.print("[dim]Created tests/[/dim]")
        return

    if stack_family == "javascript":
        if not (project_dir / "package.json").exists():
            result = _run_command(["bun", "init", "-y"], project_dir)
            if result and result.returncode == 0:
                console.print("[dim]Initialized bun project[/dim]")
            elif result:
                console.print(f"[yellow]bun init failed: {result.stderr.strip()}[/yellow]")

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
        result = _run_command(["git", "init"], project_dir, timeout=30)
        if result and result.returncode == 0:
            console.print("[dim]Initialized git repository[/dim]")
        elif result:
            console.print(f"[yellow]git init failed: {result.stderr.strip()}[/yellow]")

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
