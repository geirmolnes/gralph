"""Project setup and initialization."""

import re
import subprocess
from pathlib import Path

from rich.panel import Panel

from gralph import GRALPH_DIR
from gralph.utils.console import console, prompt_input
from gralph.prompts import ARCHITECT_PROMPT_FLAT, WORKER_PROMPT_TEMPLATE, COMPLEXITY_RANGES
from gralph.core.prd import validate_prd
from gralph.core.claude import (
    generate_prd_flat,
    get_interview_questions,
    parse_interview_summary,
    generate_epics,
    parse_epics,
    expand_epic,
)


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


# ---------- Interview loop ----------

def run_interview_loop(goal: str, stack: str) -> tuple[str, str]:
    """Multi-round interview. Returns (summary, complexity)."""
    console.print("\n[bold cyan]Let's clarify a few things...[/bold cyan]")
    conversation = ""

    while True:
        text, is_done, error = get_interview_questions(goal, stack, conversation)

        if error or text is None:
            console.print("[dim]Skipping interview.[/dim]")
            return "", "M"

        if is_done:
            summary, complexity = parse_interview_summary(text)
            console.print(f"\n[bold green]Got it![/bold green] Complexity: [bold]{complexity}[/bold]")
            console.print(Panel(summary, title="Interview Summary", border_style="green"))
            return summary, complexity

        # Show questions, get answers
        answers = prompt_input(
            "Questions",
            hint=text,
            required=False,
        )

        if not answers:
            # User pressed enter with no answer — force done
            console.print("[dim]Moving on with what we have.[/dim]")
            return conversation, "M"

        # Accumulate conversation
        conversation += f"Questions:\n{text}\n\nAnswers:\n{answers}\n\n"

        # Check if user typed "done" to end early
        if answers.strip().lower() == "done":
            console.print("[dim]Ending interview early.[/dim]")
            # Run one more round to get structured summary
            text, is_done, error = get_interview_questions(goal, stack, conversation)
            if is_done and text:
                summary, complexity = parse_interview_summary(text)
                console.print(f"[bold green]Complexity: {complexity}[/bold green]")
                return summary, complexity
            return conversation, "M"


# ---------- Epic generation + review ----------

def generate_and_review_epics(
    goal: str,
    stack: str,
    interview_summary: str,
    complexity: str,
    gralph_dir: Path,
) -> str:
    """Generate epics, let user review/edit, return approved epic text."""
    console.print("\n[bold green]Generating epics...[/bold green]")

    epics_text, error = generate_epics(goal, stack, interview_summary, complexity)
    if error or not epics_text:
        console.print(f"[red]Failed to generate epics: {error}[/red]")
        return ""

    # Write to epics.md for user editing
    epics_path = gralph_dir / "epics.md"
    ranges = COMPLEXITY_RANGES.get(complexity, COMPLEXITY_RANGES["M"])
    lo_e, hi_e = ranges["epics"]
    lo_t, hi_t = ranges["tasks_per_epic"]
    header = f"# Epics\n\nComplexity: {complexity} ({lo_e}-{hi_e} epics, ~{lo_e*lo_t}-{hi_e*hi_t} total tasks)\n\n"
    epics_path.write_text(header + epics_text + "\n")

    while True:
        # Re-read from file (user may have edited it)
        current_text = epics_path.read_text()
        display_text = current_text

        console.print(Panel(display_text, title="Epics", border_style="cyan"))

        feedback = prompt_input(
            "Review epics",
            hint="Press Enter to approve, type feedback to regenerate, or edit epics.md directly then press Enter.",
            required=False,
        )

        if not feedback:
            # Re-read in case user edited the file
            final_text = epics_path.read_text()
            # Strip the header to get just epic content
            return _strip_epics_header(final_text)

        # Regenerate with feedback
        console.print("[dim]Regenerating epics with your feedback...[/dim]")
        augmented_summary = f"{interview_summary}\n\nUser feedback on epics:\n{feedback}"
        epics_text, error = generate_epics(goal, stack, augmented_summary, complexity)
        if error or not epics_text:
            console.print(f"[yellow]Regeneration failed: {error}. Keeping current epics.[/yellow]")
            return _strip_epics_header(epics_path.read_text())

        epics_path.write_text(header + epics_text + "\n")


def _strip_epics_header(text: str) -> str:
    """Strip the metadata header from epics.md, returning just epic content."""
    lines = text.splitlines()
    # Skip lines until we hit the first ## header
    for i, line in enumerate(lines):
        if line.strip().startswith("## "):
            return "\n".join(lines[i:]).strip()
    return text.strip()


# ---------- Epic expansion ----------

def expand_all_epics(
    goal: str,
    stack: str,
    epics_text: str,
    interview_summary: str,
    complexity: str,
) -> str:
    """Expand all epics into atomic tasks. Returns full PRD task text."""
    epics = parse_epics(epics_text)
    if not epics:
        console.print("[red]No epics found to expand.[/red]")
        return ""

    ranges = COMPLEXITY_RANGES.get(complexity, COMPLEXITY_RANGES["M"])
    lo, hi = ranges["tasks_per_epic"]
    task_target = (lo + hi) // 2  # aim for midpoint

    all_sections: list[str] = []

    for i, epic in enumerate(epics, 1):
        console.print(f"[dim]Expanding epic {i}/{len(epics)}: {epic['name']}...[/dim]")
        tasks, error = expand_epic(goal, stack, epic, epics_text, task_target)

        if error or not tasks:
            console.print(f"[yellow]Failed to expand '{epic['name']}': {error}[/yellow]")
            continue

        section = f"## {epic['name']}\n{tasks}"
        all_sections.append(section)

    full_tasks = "\n\n".join(all_sections)

    # Show result and let user approve or give feedback
    console.print(Panel(full_tasks, title="Full Task Plan", border_style="cyan"))

    feedback = prompt_input(
        "Review tasks",
        hint="Press Enter to approve, or type feedback (e.g. 'expand epic 2', 'too many setup tasks').",
        required=False,
    )

    if feedback:
        # Regenerate specific epic if user mentions one, otherwise regenerate all
        epic_match = re.search(r"epic\s*(\d+)", feedback, re.IGNORECASE)
        if epic_match:
            idx = int(epic_match.group(1)) - 1
            if 0 <= idx < len(epics):
                console.print(f"[dim]Regenerating epic {idx+1}: {epics[idx]['name']}...[/dim]")
                augmented_epic = {
                    "name": epics[idx]["name"],
                    "description": f"{epics[idx]['description']}\n\nUser feedback: {feedback}",
                }
                tasks, error = expand_epic(goal, stack, augmented_epic, epics_text, task_target)
                if tasks and not error:
                    all_sections[idx] = f"## {epics[idx]['name']}\n{tasks}"
                    full_tasks = "\n\n".join(all_sections)
        else:
            # Regenerate all with feedback in context
            console.print("[dim]Regenerating all tasks with feedback...[/dim]")
            all_sections = []
            for i, epic in enumerate(epics, 1):
                augmented_epic = {
                    "name": epic["name"],
                    "description": f"{epic['description']}\n\nUser feedback: {feedback}",
                }
                tasks, error = expand_epic(goal, stack, augmented_epic, epics_text, task_target)
                if tasks and not error:
                    all_sections.append(f"## {epic['name']}\n{tasks}")
            full_tasks = "\n\n".join(all_sections)

    return full_tasks


# ---------- Planning session orchestrator ----------

def run_planning_session(
    goal: str,
    stack: str,
    skip_clarify: bool = False,
    gralph_dir: Path | None = None,
) -> str | None:
    """Full hierarchical planning: interview → epics → expand. Returns PRD task text."""
    if gralph_dir is None:
        gralph_dir = Path.cwd() / GRALPH_DIR

    # Step 1: interview
    if not skip_clarify:
        interview_summary, complexity = run_interview_loop(goal, stack)
    else:
        interview_summary, complexity = "", "M"

    console.print("\n[bold green]Planning...[/bold green]")

    # Step 2: generate & review epics
    epics_text = generate_and_review_epics(goal, stack, interview_summary, complexity, gralph_dir)
    if not epics_text:
        return None

    # Step 3: expand epics into atomic tasks
    full_tasks = expand_all_epics(goal, stack, epics_text, interview_summary, complexity)
    if not full_tasks:
        return None

    return full_tasks


# ---------- Main setup entry point ----------

def core_setup(goal: str, stack: str, skip_clarify: bool = False, project_dir: Path | None = None) -> bool:
    """Core setup logic shared between init and bootstrap."""
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

    init_package_manager(stack, project_dir)
    setup_gitignore(project_dir)

    # --quick mode: single-shot flat generation (old behavior)
    if skip_clarify:
        console.print("\n[bold green]Planning (quick mode)...[/bold green]")
        ai_prd, error = generate_prd_flat(goal, stack)
        if error:
            console.print(f"[red]Failed to generate PRD: {error}[/red]")
            return False
        if "|||" not in ai_prd:
            console.print("[red]Error: AI failed to format the PRD correctly.[/red]")
            console.print(Panel(ai_prd, title="Raw Output"))
            return False
    else:
        # Full hierarchical planning
        ai_prd = run_planning_session(goal, stack, skip_clarify=False, gralph_dir=gralph_dir)
        if not ai_prd:
            console.print("[red]Planning failed.[/red]")
            return False
        if "|||" not in ai_prd:
            console.print("[red]Error: AI failed to format tasks correctly.[/red]")
            console.print(Panel(ai_prd, title="Raw Output"))
            return False

    is_valid, errors = validate_prd(ai_prd)
    if not is_valid:
        console.print("[yellow]PRD has format issues:[/yellow]")
        for err in errors:
            console.print(f"  [dim]- {err}[/dim]")
        console.print(f"[yellow]Edit {GRALPH_DIR}/PRD.md before running.[/yellow]")

    # Write PRD
    prd_content = f"# PRD: {goal}\n\nStack: {stack}\n\n{ai_prd}"
    (gralph_dir / "PRD.md").write_text(prd_content)

    # Write worker prompt
    prompt_content = WORKER_PROMPT_TEMPLATE.format(goal=goal, stack=stack)
    (gralph_dir / "PROMPT.md").write_text(prompt_content)

    # Initialize progress file
    progress_content = """# gralph Progress Log

## Evergreen

## Learnings
"""
    (gralph_dir / "progress.txt").write_text(progress_content)

    console.print(
        Panel.fit(
            f"[green]Project gralph-ified![/green]\n\n"
            f"[bold]{GRALPH_DIR}/[/bold]\n"
            f"  |- PRD.md        [dim]# Task list[/dim]\n"
            f"  |- PROMPT.md     [dim]# Context for Claude[/dim]\n"
            f"  |_ progress.txt  [dim]# Evergreen + Learnings memory[/dim]\n\n"
            f"[bold]gralph run[/bold]      Start the loop\n"
            f"[bold]gralph status[/bold]   Show progress\n"
            f"[bold]gralph skip[/bold]     Skip current task\n"
            f"[bold]gralph edit[/bold]     Edit PRD",
            title="gralph",
        )
    )

    return True
