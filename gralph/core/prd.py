"""PRD parsing, validation, and task state operations."""

import re
from pathlib import Path


def validate_prd(prd_text: str) -> tuple[bool, list[str]]:
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
                parts = line.rsplit("|||", 1)
                if len(parts) != 2:
                    errors.append(f"Line {i}: Invalid format")
                elif not parts[1].strip():
                    errors.append(f"Line {i}: Empty verification command")

    if task_count == 0:
        errors.append("No tasks found in PRD")

    return len(errors) == 0, errors


def parse_current_task(prd_text: str) -> str | None:
    """Extract the current (first unchecked) task description."""
    match = re.search(r"^- \[ \] (.+?) \|\|\|", prd_text, re.MULTILINE)
    return match.group(1) if match else None


def parse_all_tasks(prd_text: str) -> list[tuple[str, str]]:
    """Return list of (status_char, description) for all tasks."""
    return re.findall(r"^- \[([x~! ])\] (.+?) \|\|\|", prd_text, re.MULTILINE)


def count_tasks(prd_text: str) -> dict[str, int]:
    """Count tasks by status."""
    return {
        "completed": len(re.findall(r"^- \[x\]", prd_text, re.MULTILINE)),
        "skipped": len(re.findall(r"^- \[~\]", prd_text, re.MULTILINE)),
        "failed": len(re.findall(r"^- \[!\]", prd_text, re.MULTILINE)),
        "pending": len(re.findall(r"^- \[ \]", prd_text, re.MULTILINE)),
    }


def mark_task(prd_path: Path, status: str) -> str | None:
    """
    Mark the current task with the given status.
    
    Args:
        prd_path: Path to PRD.md
        status: One of 'x' (done), '~' (skipped), '!' (failed)
    
    Returns:
        The task description that was marked, or None if no pending task.
    """
    text = prd_path.read_text()
    match = re.search(r"^- \[ \] (.+?) \|\|\|", text, re.MULTILINE)
    if not match:
        return None
    
    new_text = re.sub(r"^- \[ \]", f"- [{status}]", text, count=1, flags=re.MULTILINE)
    prd_path.write_text(new_text)
    return match.group(1)


def append_tasks(prd_path: Path, new_tasks: str) -> int:
    """Append new tasks to the PRD. Returns count of tasks added."""
    task_lines = [l for l in new_tasks.strip().split("\n") if l.strip().startswith("- [ ]")]
    if not task_lines:
        return 0
    text = prd_path.read_text().rstrip()
    text += "\n" + "\n".join(task_lines) + "\n"
    prd_path.write_text(text)
    return len(task_lines)


def reset_all_tasks(prd_path: Path) -> None:
    """Reset all tasks to pending status."""
    text = prd_path.read_text()
    new_text = re.sub(r"^- \[[x~!]\]", "- [ ]", text, flags=re.MULTILINE)
    prd_path.write_text(new_text)
