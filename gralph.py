#!/usr/bin/env python3
"""
gralph - Geir's Ralph Loop Scaffolding Tool

Sets up and manages autonomous coding sessions with sandboxed execution.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


try:
    import typer
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError:
    print("Missing dependencies. Run: pip install typer rich")
    sys.exit(1)

__version__ = "0.5.0"
GRALPH_DIR = "gralph"
REQUIRED_TOOLS = {
    "claude": "Install Claude Code: https://docs.anthropic.com/claude-code",
}

app = typer.Typer(
    name="gralph", help="Scaffold and run Ralph coding loops", invoke_without_command=True
)
@app.callback()
def main(ctx: typer.Context):
    """gralph CLI entrypoint."""
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit(0)

console = Console()


def _show_version():
    """Display version banner."""
    console.print(f"[bold cyan]gralph[/bold cyan] v{__version__}")


ARCHITECT_PROMPT = """You are a Lead Software Architect. I want to build: "{goal}"
Stack: {stack} (use 'uv' for python, 'bun' for javascript).

Break this down into a list of ATOMIC, SEQUENTIAL tasks.
Each task must have a verifiable check command.

CRITICAL FORMAT RULES:
- Output ONLY a markdown checklist. No introduction. No explanation. No code blocks.
- Start your response with "- [ ]" on line 1.
- Each line: - [ ] <description> ||| <verification_command>
- Use EXACTLY ONE ||| separator per line.
- Verification commands must return exit code 0 on success.
- Use ONLY `uv` or `bun` for package management.

Example output (follow this format exactly):
- [ ] Create main.py with hello world ||| python3 main.py | grep -q "hello"
- [ ] Install requests library ||| uv pip show requests
- [ ] Add CLI argument parsing ||| python3 main.py --help | grep -q "usage"
"""

RALPH_SH = r"""#!/bin/bash
set -e

MAX_ITERATIONS=${1:-20}
COMPLETION_PROMISE=${2:-<promise>COMPLETE</promise>}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🚀 gralph loop starting"
echo "   Project: $PROJECT_ROOT"
echo "   Max iterations: $MAX_ITERATIONS"

cd "$PROJECT_ROOT"

for ((i=1; i<=$MAX_ITERATIONS; i++)); do
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo "  Iteration $i / $MAX_ITERATIONS"
    echo "════════════════════════════════════════════════════════════"
    
    PROMPT="@gralph/PRD.md @gralph/progress.txt @gralph/PROMPT.md
1. Find the highest-priority unchecked task (- [ ]) and implement it.
2. Run the verification command for that task.
3. If verification passes, mark the task done: change '- [ ]' to '- [x]' in PRD.md.
4. Append what you learned to progress.txt.
5. Commit your changes with a descriptive message.
ONLY WORK ON A SINGLE TASK PER ITERATION.
If all tasks are complete (no more '- [ ]'), output: $COMPLETION_PROMISE"

    result=$(claude --dangerously-skip-permissions --print "$PROMPT" 2>&1) || true
    
    echo "$result"
    
    if [[ "$result" == *"$COMPLETION_PROMISE"* ]]; then
        echo ""
        echo "✅ PRD complete after $i iterations!"
        exit 0
    fi
done

echo ""
echo "⚠️  Reached max iterations ($MAX_ITERATIONS). Some tasks may be incomplete."
echo "Review gralph/PRD.md and run 'gralph run' again if needed."
"""


def _check_dependencies() -> list[str]:
    """Check for required external tools and return list of missing ones."""
    missing = []
    for tool, install_hint in REQUIRED_TOOLS.items():
        if not shutil.which(tool):
            missing.append(f"{tool}: {install_hint}")
    return missing


def _find_gralph_dir() -> Path | None:
    """Find the gralph directory in current or parent directories, stopping at git root."""
    current = Path.cwd()
    for _ in range(10):
        gralph_path = current / GRALPH_DIR
        if gralph_path.is_dir() and (gralph_path / "PRD.md").exists():
            return gralph_path
        # Stop at git root
        if (current / ".git").exists():
            break
        if current.parent == current:
            break
        current = current.parent
    return None


def _validate_prd(prd_text: str) -> tuple[bool, list[str]]:
    """Validate that the PRD follows the expected format."""
    lines = prd_text.strip().split("\n")
    errors = []
    task_count = 0

    for i, line in enumerate(lines, 1):
        line = line.strip()
        if line.startswith("- [ ]"):
            task_count += 1
            if "|||" not in line:
                errors.append(f"Line {i}: Missing ||| separator")
            else:
                # Split on last ||| to handle edge cases
                parts = line.rsplit("|||", 1)
                if len(parts) != 2:
                    errors.append(f"Line {i}: Invalid format")
                elif not parts[1].strip():
                    errors.append(f"Line {i}: Empty verification command")

    if task_count == 0:
        errors.append("No tasks found in PRD")

    return len(errors) == 0, errors


def _core_setup(goal: str, stack: str):
    """Core setup logic shared between init and bootstrap."""
    gralph_dir = Path(GRALPH_DIR)
    gralph_dir.mkdir(exist_ok=True)

    if not Path(".git").exists():
        subprocess.run(["git", "init"], capture_output=True)
        console.print("[dim]Initialized git repository[/dim]")

    # Ignore internal state files - PRD.md and progress.txt should be tracked
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

    console.print("[bold green]🧠 gralph is planning...[/bold green]")
    prompt = ARCHITECT_PROMPT.format(goal=goal, stack=stack)
    
    cmd = ["claude", "--print", prompt]
    result = subprocess.run(cmd, capture_output=True, text=True)
    ai_prd = result.stdout.strip()
    
    if result.returncode != 0:
        console.print(f"[red]Failed to generate PRD[/red]")
        if result.stderr:
            console.print(f"[dim]{result.stderr[:500]}[/dim]")
        raise typer.Exit(1)

    # Strip markdown code blocks if present
    if ai_prd.startswith("```"):
        lines = ai_prd.split("\n")
        ai_prd = "\n".join(line for line in lines if not line.startswith("```"))

    # Quick sanity check
    if "|||" not in ai_prd:
        console.print("[red]Error: AI failed to format the PRD correctly.[/red]")
        console.print(Panel(ai_prd, title="Raw Output"))
        raise typer.Exit(1)

    # Detailed validation
    is_valid, errors = _validate_prd(ai_prd)
    if not is_valid:
        console.print("[yellow]⚠️  PRD has format issues:[/yellow]")
        for err in errors:
            console.print(f"  [dim]• {err}[/dim]")
        console.print("[yellow]Edit gralph/PRD.md before running.[/yellow]")

    prd_content = f"# PRD: {goal}\n\nStack: {stack}\n\n{ai_prd}"
    (gralph_dir / "PRD.md").write_text(prd_content)

    prompt_content = f"""# gralph Worker Context

## Project Goal
{goal}

## Technology Stack
{stack}

## Instructions
You are implementing a project step by step. Focus only on the current task.
Write clean, working code. Make the verification command pass.
Do not modify files unrelated to the current task.
Only when you are truly done, output the completion promise provided in the task context
- Only work on a single task per iteration.
- Update PRD.md with progress for that task.
- Append learnings to progress.txt (patterns at the top).
- Auth: docker sandbox persists Claude login inside its volume.

## Important
- If you discover something useful, mention it so it can be logged.
- If a task seems impossible, explain why clearly.
- Check existing files before creating new ones.
- Log learnings in progress.txt; put reusable patterns in ## Codebase Patterns at the top.
"""
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

    script_path = gralph_dir / "ralph.sh"
    script_path.write_text(RALPH_SH)
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


@app.command()
def init(
    name: str = typer.Argument(..., help="Project directory name"),
    goal: Optional[str] = typer.Option(
        None, "--goal", "-g", help="What to build", prompt=True
    ),
    stack: Optional[str] = typer.Option(
        "python", "--stack", "-s", help="Tech stack", prompt=True
    ),
):
    """Create a new project and initialize gralph."""
    path = Path(name)
    if path.exists():
        console.print(f"[red]Directory '{name}' already exists[/red]")
        raise typer.Exit(1)

    path.mkdir()
    os.chdir(path)
    console.print(f"[dim]Created: {name}[/dim]")
    _core_setup(goal, stack)
    console.print(f"[bold]Next:[/bold] cd {name}")


@app.command()
def bootstrap(
    goal: Optional[str] = typer.Option(
        None, "--goal", "-g", help="What to build", prompt=True
    ),
    stack: Optional[str] = typer.Option(
        "python", "--stack", "-s", help="Tech stack", prompt=True
    ),
):
    """Initialize gralph in current directory."""
    _show_version()

    if Path(GRALPH_DIR).exists() and (Path(GRALPH_DIR) / "PRD.md").exists():
        console.print(
            "[yellow]Already gralph-ified. Use 'gralph run' or delete gralph/[/yellow]"
        )
        raise typer.Exit(1)

    _core_setup(goal, stack)


@app.command()
def run(
    max_iterations: int = typer.Option(20, "--max", "-m", help="Max iterations"),
    completion_promise: str = typer.Option(
        "<promise>COMPLETE</promise>",
        "--promise",
        "-p",
        help="Completion promise token",
    ),
):
    """Run the Ralph loop using Claude's native sandboxing."""
    _show_version()

    gralph_dir = _find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        console.print(
            "Run [bold]gralph init[/bold] or [bold]gralph bootstrap[/bold] first."
        )
        raise typer.Exit(1)

    script = gralph_dir / "ralph.sh"
    os.chdir(gralph_dir.parent)
    console.print(f"[bold green]🍩 Running from:[/bold green] {gralph_dir.parent.name}")

    try:
        subprocess.run(
            [
                str(script),
                str(max_iterations),
                completion_promise,
            ],
            check=True,
        )
    except subprocess.CalledProcessError:
        console.print("[red]Loop aborted.[/red]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Loop paused. Run 'gralph run' to resume.[/yellow]")


@app.command()
def status():
    """Show progress."""
    gralph_dir = _find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    prd_text = (gralph_dir / "PRD.md").read_text()

    completed = len(re.findall(r"^- \[x\]", prd_text, re.MULTILINE))
    skipped = len(re.findall(r"^- \[~\]", prd_text, re.MULTILINE))
    failed = len(re.findall(r"^- \[!\]", prd_text, re.MULTILINE))
    pending = len(re.findall(r"^- \[ \]", prd_text, re.MULTILINE))
    total = completed + skipped + failed + pending

    current_match = re.search(r"^- \[ \] (.+?) \|\|\|", prd_text, re.MULTILINE)

    table = Table(title="gralph Status")
    table.add_column("", style="bold")
    table.add_column("")

    table.add_row("✅ Done", f"[green]{completed}[/green]")
    table.add_row("⏭️  Skip", f"[yellow]{skipped}[/yellow]")
    table.add_row("❌ Fail", f"[red]{failed}[/red]")
    table.add_row("⏳ Todo", f"{pending}")

    if total > 0:
        table.add_row("📈 Progress", f"{(completed / total) * 100:.0f}%")

    console.print(table)

    if current_match:
        console.print(f"\n[bold]Next:[/bold] {current_match.group(1)}")
    elif pending == 0:
        console.print("\n[green]All tasks complete![/green]")

    # Show state if paused mid-task
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


@app.command()
def skip():
    """Skip current task."""
    gralph_dir = _find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    prd_path = gralph_dir / "PRD.md"
    text = prd_path.read_text()

    match = re.search(r"^- \[ \] (.+?) \|\|\|", text, re.MULTILINE)
    if not match:
        console.print("[yellow]No pending tasks.[/yellow]")
        raise typer.Exit(0)

    prd_path.write_text(
        re.sub(r"^- \[ \]", "- [~]", text, count=1, flags=re.MULTILINE)
    )
    console.print(f"[yellow]⏭️  Skipped:[/yellow] {match.group(1)}")

    (gralph_dir / ".ralph_error.txt").unlink(missing_ok=True)
    (gralph_dir / ".ralph_state.json").unlink(missing_ok=True)


@app.command()
def done():
    """Mark current task done manually."""
    gralph_dir = _find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    prd_path = gralph_dir / "PRD.md"
    text = prd_path.read_text()

    match = re.search(r"^- \[ \] (.+?) \|\|\|", text, re.MULTILINE)
    if not match:
        console.print("[yellow]No pending tasks.[/yellow]")
        raise typer.Exit(0)

    prd_path.write_text(
        re.sub(r"^- \[ \]", "- [x]", text, count=1, flags=re.MULTILINE)
    )
    console.print(f"[green]✅ Done:[/green] {match.group(1)}")

    (gralph_dir / ".ralph_error.txt").unlink(missing_ok=True)
    (gralph_dir / ".ralph_state.json").unlink(missing_ok=True)


@app.command()
def edit():
    """Open PRD in editor."""
    gralph_dir = _find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    editor = os.environ.get("EDITOR", "nano")
    subprocess.run([editor, str(gralph_dir / "PRD.md")])


@app.command()
def log(
    message: str = typer.Argument(..., help="Message to add to progress log"),
):
    """Add a manual note to the progress log."""
    gralph_dir = _find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    progress_file = gralph_dir / "progress.txt"
    with open(progress_file, "a") as f:
        f.write(f"\n## [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] NOTE\n")
        f.write(f"{message}\n")

    console.print("[green]✏️  Logged.[/green]")


@app.command()
def reset():
    """Reset all tasks to pending."""
    gralph_dir = _find_gralph_dir()
    if not gralph_dir:
        console.print("[red]Not a gralph project.[/red]")
        raise typer.Exit(1)

    if not typer.confirm("Reset all tasks to pending?"):
        raise typer.Abort()

    prd_path = gralph_dir / "PRD.md"
    text = prd_path.read_text()
    prd_path.write_text(re.sub(r"^- \[[x~!]\]", "- [ ]", text, flags=re.MULTILINE))

    (gralph_dir / ".ralph_error.txt").unlink(missing_ok=True)
    (gralph_dir / ".ralph_state.json").unlink(missing_ok=True)
    (gralph_dir / ".ralph_retries.txt").unlink(missing_ok=True)
    console.print("[green]All tasks reset.[/green]")


@app.command()
def doctor():
    """Check system dependencies and configuration."""
    console.print("[bold]Checking dependencies...[/bold]\n")

    all_ok = True
    for tool, install_hint in REQUIRED_TOOLS.items():
        path = shutil.which(tool)
        if path:
            console.print(f"  [green]✓[/green] {tool}: {path}")
        else:
            console.print(f"  [red]✗[/red] {tool}: NOT FOUND")
            console.print(f"    [dim]{install_hint}[/dim]")
            all_ok = False

    # Check podman machine status on macOS
    if sys.platform == "darwin" and shutil.which("podman"):
        console.print("\n[bold]Checking podman machine...[/bold]")
        result = subprocess.run(
            ["podman", "machine", "list", "--format", "{{.Running}}"],
            capture_output=True,
            text=True,
        )
        if "true" in result.stdout.lower():
            console.print("  [green]✓[/green] Podman machine is running")
        else:
            console.print("  [yellow]![/yellow] Podman machine not running")
            console.print("    [dim]Run: podman machine start[/dim]")

    if all_ok:
        console.print("\n[green]All dependencies satisfied![/green]")
    else:
        console.print(
            "\n[yellow]Some dependencies missing. Install them before running.[/yellow]"
        )
        raise typer.Exit(1)


@app.command()
def version():
    """Show gralph version."""
    _show_version()


if __name__ == "__main__":
    app()
