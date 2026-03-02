"""Agent team execution for a single task."""

from pathlib import Path

from gralph.core.prd import TaskEntry
from gralph.core.docker import run_claude_docker_interactive
from gralph.core.progress import build_memory_snapshot
from gralph.prompts import TEAM_PROMPT_TEMPLATE


def _build_team_prompt(task: TaskEntry, prompt_md: str, memory_snapshot: str) -> str:
    """Format team prompt with task fields and project context."""
    return TEAM_PROMPT_TEMPLATE.format(
        task_id=task.task_id,
        description=task.description,
        verification=task.verification,
        prompt_md=prompt_md,
        memory_snapshot=memory_snapshot,
    )


def run_team_task(
    task: TaskEntry,
    gralph_dir: Path,
    project_dir: Path,
    model: str,
) -> bool:
    """Run an agent team session for a single task. Returns True on success."""
    prompt_md_path = gralph_dir / "PROMPT.md"
    prompt_md = prompt_md_path.read_text() if prompt_md_path.exists() else ""
    memory_snapshot = build_memory_snapshot(gralph_dir / "progress.txt")

    prompt = _build_team_prompt(task, prompt_md, memory_snapshot)
    exit_code = run_claude_docker_interactive(
        prompt=prompt,
        model=model,
        project_dir=project_dir,
    )
    return exit_code == 0
