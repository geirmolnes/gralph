"""PRD parsing, validation, and task state operations."""

import re
from pathlib import Path

TASK_LINE_RE = re.compile(r"^- \[([ xX~!])\](.*)$")
CANONICAL_TASK_RE = re.compile(r"^- \[([x~! ])\] (.+?) \|\|\|", re.MULTILINE)
PENDING_TASK_RE = re.compile(r"^- \[ \] (.+?) \|\|\|", re.MULTILINE)


def lint_prd(prd_text: str) -> list[str]:
    """Return human-readable PRD formatting errors with line numbers."""
    errors: list[str] = []

    for i, raw_line in enumerate(prd_text.splitlines(), 1):
        line = raw_line.strip()
        if not line.startswith("- ["):
            continue

        match = TASK_LINE_RE.match(line)
        if not match:
            errors.append(
                f"Line {i}: Invalid checkbox format (expected '- [ ]', '- [x]', '- [~]', or '- [!]')."
            )
            continue

        status, remainder = match.groups()
        if status == "X":
            errors.append(f"Line {i}: Use lowercase 'x' for completed tasks.")

        remainder = remainder.strip()
        if "|||" not in remainder:
            errors.append(f"Line {i}: Missing ||| separator")
            continue

        description, verification = remainder.rsplit("|||", 1)
        if not description.strip():
            errors.append(f"Line {i}: Empty task description")
        if not verification.strip():
            errors.append(f"Line {i}: Empty verification command")

    return errors


def fix_prd_format(prd_text: str) -> tuple[str, int]:
    """Normalize task lines to canonical format. Returns (new_text, fixes_applied)."""
    had_trailing_newline = prd_text.endswith("\n")
    fixed_lines: list[str] = []
    fixes = 0

    for raw_line in prd_text.splitlines():
        stripped = raw_line.strip()
        match = TASK_LINE_RE.match(stripped)
        if not match:
            fixed_lines.append(raw_line)
            continue

        status, remainder = match.groups()
        if "|||" not in remainder:
            fixed_lines.append(raw_line)
            continue

        description, verification = remainder.rsplit("|||", 1)
        normalized_status = status.lower()
        normalized = f"- [{normalized_status}] {description.strip()} ||| {verification.strip()}"

        fixed_lines.append(normalized)
        if normalized != raw_line:
            fixes += 1

    out = "\n".join(fixed_lines)
    if had_trailing_newline:
        out += "\n"
    return out, fixes


def validate_prd(prd_text: str) -> tuple[bool, list[str]]:
    """Validate that the PRD follows the expected format."""
    errors = lint_prd(prd_text)
    task_count = len(PENDING_TASK_RE.findall(prd_text))

    if task_count == 0:
        errors.append("No tasks found in PRD")

    return len(errors) == 0, errors


def parse_current_task(prd_text: str) -> str | None:
    """Extract the current (first unchecked) task description."""
    match = PENDING_TASK_RE.search(prd_text)
    return match.group(1) if match else None


def parse_all_tasks(prd_text: str) -> list[tuple[str, str]]:
    """Return list of (status_char, description) for all tasks."""
    return CANONICAL_TASK_RE.findall(prd_text)


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
