"""PRD parsing, validation, and task state operations."""

from dataclasses import dataclass
from pathlib import Path
import re
import secrets

TASK_LINE_RE = re.compile(r"^- \[([ xX~!])\](.*)$")
TASK_ID_TAG_RE = re.compile(r"\[id:([A-Za-z0-9._:-]+)\]")
TASK_DEPS_TAG_RE = re.compile(r"\[deps:([A-Za-z0-9._:,\- ]+)\]")


@dataclass(frozen=True)
class TaskEntry:
    """Parsed PRD task entry."""

    status: str
    description: str
    verification: str
    task_id: str | None
    deps: tuple[str, ...]


def _split_task_remainder(remainder: str) -> tuple[str, str] | None:
    """Split '<description> ||| <verification>' into parts."""
    if "|||" not in remainder:
        return None
    description, verification = remainder.rsplit("|||", 1)
    return description, verification


def extract_task_metadata(description: str) -> tuple[str, str | None, list[str]]:
    """Extract metadata tags from a task description."""
    task_id_match = TASK_ID_TAG_RE.search(description)
    deps_match = TASK_DEPS_TAG_RE.search(description)

    task_id = task_id_match.group(1) if task_id_match else None
    deps: list[str] = []
    if deps_match:
        deps = [d.strip() for d in deps_match.group(1).split(",") if d.strip()]

    clean = TASK_ID_TAG_RE.sub("", description)
    clean = TASK_DEPS_TAG_RE.sub("", clean)
    clean = re.sub(r"\s{2,}", " ", clean).strip()
    return clean, task_id, deps


def parse_task_entries(prd_text: str) -> list[TaskEntry]:
    """Parse all valid task lines from PRD text."""
    tasks: list[TaskEntry] = []
    for raw_line in prd_text.splitlines():
        line = raw_line.strip()
        match = TASK_LINE_RE.match(line)
        if not match:
            continue

        status, remainder = match.groups()
        parts = _split_task_remainder(remainder)
        if not parts:
            continue

        description, verification = parts
        clean_desc, task_id, deps = extract_task_metadata(description.strip())
        normalized_status = status.lower() if status != " " else " "
        tasks.append(
            TaskEntry(
                status=normalized_status,
                description=clean_desc or description.strip(),
                verification=verification.strip(),
                task_id=task_id,
                deps=tuple(deps),
            )
        )
    return tasks


def find_task_by_id(prd_text: str, task_id: str) -> TaskEntry | None:
    """Find a task by id."""
    for task in parse_task_entries(prd_text):
        if task.task_id == task_id:
            return task
    return None


def get_task_status_by_id(prd_text: str, task_id: str) -> str | None:
    """Return task status for a given id."""
    task = find_task_by_id(prd_text, task_id)
    return task.status if task else None


def get_ready_tasks(
    prd_text: str,
    unavailable_task_ids: set[str] | None = None,
) -> list[TaskEntry]:
    """
    Return pending tasks whose dependencies are satisfied.

    `unavailable_task_ids` can be used to exclude already-claimed tasks.
    """
    unavailable = unavailable_task_ids or set()
    tasks = parse_task_entries(prd_text)
    terminal_ids = {t.task_id for t in tasks if t.status in {"x", "~", "!"} and t.task_id}

    ready: list[TaskEntry] = []
    for task in tasks:
        if task.status != " ":
            continue
        if task.task_id and task.task_id in unavailable:
            continue
        if not task.deps or all(dep in terminal_ids for dep in task.deps):
            ready.append(task)
    return ready


def _generate_task_id(existing_ids: set[str], prefix: str = "g") -> str:
    """Generate a collision-resistant short task id."""
    while True:
        candidate = f"{prefix}-{secrets.token_hex(2)}"
        if candidate not in existing_ids:
            return candidate


def ensure_task_ids(prd_text: str, prefix: str = "g") -> tuple[str, int]:
    """
    Ensure every valid task line has a unique [id:...] tag.

    Returns (new_text, ids_updated).
    """
    had_trailing_newline = prd_text.endswith("\n")
    lines = prd_text.splitlines()
    used_ids: set[str] = set()
    updated = 0

    for i, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        match = TASK_LINE_RE.match(stripped)
        if not match:
            continue

        status, remainder = match.groups()
        parts = _split_task_remainder(remainder)
        if not parts:
            continue

        description, verification = parts
        description = description.strip()
        verification = verification.strip()
        normalized_status = status.lower() if status != " " else " "

        id_match = TASK_ID_TAG_RE.search(description)
        if not id_match:
            task_id = _generate_task_id(used_ids, prefix=prefix)
            used_ids.add(task_id)
            description = f"[id:{task_id}] {description}" if description else f"[id:{task_id}]"
            updated += 1
        else:
            task_id = id_match.group(1)
            if task_id in used_ids:
                replacement = _generate_task_id(used_ids, prefix=prefix)
                description = TASK_ID_TAG_RE.sub(f"[id:{replacement}]", description, count=1)
                used_ids.add(replacement)
                updated += 1
            else:
                used_ids.add(task_id)

        lines[i] = f"- [{normalized_status}] {description} ||| {verification}"

    out = "\n".join(lines)
    if had_trailing_newline:
        out += "\n"
    return out, updated


def lint_prd(prd_text: str) -> list[str]:
    """Return human-readable PRD formatting errors with line numbers."""
    errors: list[str] = []
    seen_task_ids: dict[str, int] = {}

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
        parts = _split_task_remainder(remainder)
        if not parts:
            errors.append(f"Line {i}: Missing ||| separator")
            continue

        description, verification = parts
        if not description.strip():
            errors.append(f"Line {i}: Empty task description")
        if not verification.strip():
            errors.append(f"Line {i}: Empty verification command")
        _, task_id, _ = extract_task_metadata(description.strip())
        if task_id:
            first_line = seen_task_ids.get(task_id)
            if first_line is None:
                seen_task_ids[task_id] = i
            else:
                errors.append(
                    f"Line {i}: Duplicate task id '{task_id}' (first seen on line {first_line})."
                )
        if description.strip() and verification.strip():
            canonical = f"{description.strip()} ||| {verification.strip()}"
            if remainder != canonical:
                errors.append(
                    f"Line {i}: Use canonical task format '<description> ||| <verification command>'."
                )

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
        parts = _split_task_remainder(remainder)
        if not parts:
            fixed_lines.append(raw_line)
            continue

        description, verification = parts
        normalized_status = status.lower() if status != " " else " "
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
    task_count = len([t for t in parse_task_entries(prd_text) if t.status == " "])

    if task_count == 0:
        errors.append("No tasks found in PRD")

    return len(errors) == 0, errors


def parse_current_task(prd_text: str) -> str | None:
    """Extract the current (first unchecked) task description."""
    for task in parse_task_entries(prd_text):
        if task.status == " ":
            return task.description
    return None


def parse_all_tasks(prd_text: str) -> list[tuple[str, str]]:
    """Return list of (status_char, clean_description) for all tasks."""
    return [(task.status, task.description) for task in parse_task_entries(prd_text)]


def count_tasks(prd_text: str) -> dict[str, int]:
    """Count tasks by status."""
    return {
        "completed": len(re.findall(r"^- \[x\]", prd_text, re.MULTILINE)),
        "skipped": len(re.findall(r"^- \[~\]", prd_text, re.MULTILINE)),
        "failed": len(re.findall(r"^- \[!\]", prd_text, re.MULTILINE)),
        "pending": len(re.findall(r"^- \[ \]", prd_text, re.MULTILINE)),
    }


def mark_task_by_id(prd_path: Path, task_id: str, status: str) -> str | None:
    """Mark a specific pending task by id."""
    text = prd_path.read_text()
    lines = text.splitlines()
    had_trailing_newline = text.endswith("\n")

    for i, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        match = TASK_LINE_RE.match(stripped)
        if not match:
            continue

        current_status, remainder = match.groups()
        parts = _split_task_remainder(remainder)
        if not parts:
            continue

        description, verification = parts
        clean_desc, existing_id, _ = extract_task_metadata(description.strip())
        if existing_id != task_id:
            continue

        if current_status != " ":
            return None

        lines[i] = f"- [{status}] {description.strip()} ||| {verification.strip()}"
        new_text = "\n".join(lines)
        if had_trailing_newline:
            new_text += "\n"
        prd_path.write_text(new_text)
        return clean_desc or description.strip()

    return None


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
    lines = text.splitlines()
    had_trailing_newline = text.endswith("\n")

    for i, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        match = TASK_LINE_RE.match(stripped)
        if not match:
            continue

        current_status, remainder = match.groups()
        parts = _split_task_remainder(remainder)
        if not parts or current_status != " ":
            continue

        description, verification = parts
        clean_desc, task_id, _ = extract_task_metadata(description.strip())
        if task_id:
            return mark_task_by_id(prd_path, task_id, status)

        lines[i] = f"- [{status}] {description.strip()} ||| {verification.strip()}"
        new_text = "\n".join(lines)
        if had_trailing_newline:
            new_text += "\n"
        prd_path.write_text(new_text)
        return clean_desc or description.strip()

    return None


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
