"""Progress log parsing and deterministic memory snapshot helpers."""

import re
from dataclasses import dataclass
from pathlib import Path


EVERGREEN_HEADING = "## Evergreen"
LEARNINGS_HEADING = "## Learnings"
RECENT_LEARNINGS_LIMIT = 10

_ITEM_RE = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$")
_EVERGREEN_RE = re.compile(r"\[\s*evergreen\s*\]", re.IGNORECASE)


@dataclass(frozen=True)
class LearningEntry:
    """One parsed learning entry from progress.txt."""

    number: int
    text: str
    evergreen: bool


def parse_learning_entries(progress_text: str) -> list[LearningEntry]:
    """Parse numbered entries from the ## Learnings section."""
    lines = progress_text.splitlines()
    return _parse_section_entries(lines, LEARNINGS_HEADING)


def parse_evergreen_entries(progress_text: str) -> list[LearningEntry]:
    """Parse evergreen entries from ## Evergreen plus legacy tagged learnings."""
    lines = progress_text.splitlines()
    explicit = _parse_section_entries(lines, EVERGREEN_HEADING)
    legacy = [
        LearningEntry(
            number=entry.number,
            text=_strip_evergreen_tag(entry.text),
            evergreen=True,
        )
        for entry in parse_learning_entries(progress_text)
        if entry.evergreen
    ]

    combined: list[LearningEntry] = []
    seen: set[str] = set()
    for entry in [*explicit, *legacy]:
        key = entry.text.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        combined.append(
            LearningEntry(
                number=entry.number,
                text=_strip_evergreen_tag(entry.text),
                evergreen=True,
            )
        )
    return combined


def append_learning(progress_path: Path, message: str, evergreen: bool = False) -> int:
    """Append a numbered learning entry and return the assigned number."""
    line = _normalize_message(message)
    if not line:
        raise ValueError("Learning message cannot be empty.")

    text = progress_path.read_text() if progress_path.exists() else _default_progress_text()
    lines = text.splitlines()
    if not lines:
        lines = _default_progress_text().splitlines()

    if _EVERGREEN_RE.search(line):
        evergreen = True
    line = _strip_evergreen_tag(line)

    lines = _ensure_progress_sections(lines)
    target_heading = EVERGREEN_HEADING if evergreen else LEARNINGS_HEADING
    section = _find_section(lines, target_heading)
    assert section is not None
    start, end = section

    max_number = 0
    for existing in lines[start:end]:
        match = _ITEM_RE.match(existing)
        if match:
            max_number = max(max_number, int(match.group(1)))

    next_number = max_number + 1
    entry = f"{next_number}. {line}"

    insertion_index = end
    while insertion_index > start and not lines[insertion_index - 1].strip():
        insertion_index -= 1
    lines.insert(insertion_index, entry)

    progress_path.write_text("\n".join(lines).rstrip() + "\n")
    return next_number


def build_memory_snapshot(progress_path: Path, recent_limit: int = RECENT_LEARNINGS_LIMIT) -> str:
    """Build deterministic memory context from progress sections."""
    if recent_limit < 1:
        raise ValueError("recent_limit must be >= 1")

    if not progress_path.exists():
        return _empty_snapshot(recent_limit)

    progress_text = progress_path.read_text()
    evergreen_entries = parse_evergreen_entries(progress_text)
    learning_entries = [
        LearningEntry(number=entry.number, text=entry.text, evergreen=False)
        for entry in parse_learning_entries(progress_text)
        if not entry.evergreen
    ]
    if not evergreen_entries and not learning_entries:
        return _empty_snapshot(recent_limit)

    recent = learning_entries[-recent_limit:]

    lines = [
        "MEMORY SNAPSHOT (_PD_/progress.txt)",
        (
            f"- deterministic ingest: all entries from {EVERGREEN_HEADING} + "
            f"last {recent_limit} entries from {LEARNINGS_HEADING}"
        ),
        "",
        f"{EVERGREEN_HEADING[3:]}:",
    ]
    if evergreen_entries:
        for entry in evergreen_entries:
            lines.append(f"- [{entry.number}] {_strip_evergreen_tag(entry.text)}")
    else:
        lines.append("- (none)")

    lines.append("")
    lines.append(f"Recent {LEARNINGS_HEADING[3:]}:")
    for entry in recent:
        lines.append(f"- [{entry.number}] {_strip_evergreen_tag(entry.text)}")
    if not recent:
        lines.append("- (none)")

    return "\n".join(lines)


def _default_progress_text() -> str:
    return f"# gralph Progress Log\n\n{EVERGREEN_HEADING}\n\n{LEARNINGS_HEADING}\n"


def _find_section(lines: list[str], heading: str) -> tuple[int, int] | None:
    start = None
    for idx, line in enumerate(lines):
        if line.strip().lower() == heading.lower():
            start = idx + 1
            break
    if start is None:
        return None

    end = len(lines)
    for idx in range(start, len(lines)):
        if lines[idx].lstrip().startswith("## "):
            end = idx
            break
    return start, end


def _find_heading_index(lines: list[str], heading: str) -> int | None:
    for idx, line in enumerate(lines):
        if line.strip().lower() == heading.lower():
            return idx
    return None


def _parse_section_entries(lines: list[str], heading: str) -> list[LearningEntry]:
    section = _find_section(lines, heading)
    if section is None:
        return []
    start, end = section
    entries: list[LearningEntry] = []
    for line in lines[start:end]:
        match = _ITEM_RE.match(line)
        if not match:
            continue
        text = match.group(2).strip()
        entries.append(
            LearningEntry(
                number=int(match.group(1)),
                text=text,
                evergreen=bool(_EVERGREEN_RE.search(text)),
            )
        )
    return entries


def _ensure_progress_sections(lines: list[str]) -> list[str]:
    if not lines:
        return _default_progress_text().splitlines()

    normalized = list(lines)
    learnings_index = _find_heading_index(normalized, LEARNINGS_HEADING)
    if learnings_index is None:
        if normalized and normalized[-1].strip():
            normalized.append("")
        normalized.append(LEARNINGS_HEADING)
        learnings_index = _find_heading_index(normalized, LEARNINGS_HEADING)
        assert learnings_index is not None

    evergreen_index = _find_heading_index(normalized, EVERGREEN_HEADING)
    if evergreen_index is None:
        insertion: list[str] = []
        if learnings_index > 0 and normalized[learnings_index - 1].strip():
            insertion.append("")
        insertion.extend([EVERGREEN_HEADING, ""])
        normalized[learnings_index:learnings_index] = insertion

    return normalized


def _normalize_message(message: str) -> str:
    parts = [part.strip() for part in message.splitlines() if part.strip()]
    return " ".join(parts)


def _strip_evergreen_tag(text: str) -> str:
    return _EVERGREEN_RE.sub("", text, count=1).strip()


def _empty_snapshot(recent_limit: int) -> str:
    return (
        "MEMORY SNAPSHOT (_PD_/progress.txt)\n"
        f"- deterministic ingest: all entries from {EVERGREEN_HEADING} + "
        f"last {recent_limit} entries from {LEARNINGS_HEADING}\n"
        "- no learnings logged yet"
    )
