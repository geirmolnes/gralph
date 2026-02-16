from gralph.core.progress import (
    build_memory_snapshot,
    append_learning,
    parse_evergreen_entries,
    parse_learning_entries,
)


def test_parse_learning_entries_reads_numbered_items_and_legacy_evergreen_tag():
    content = """# gralph Progress Log

## Evergreen
1. Durable rule from section.

## Learnings
1. [evergreen] Legacy durable rule.
2. Added parser regression test.
notes that should be ignored
10. Follow-up change.

## Other
1. Ignored section entry
"""
    entries = parse_learning_entries(content)
    assert [entry.number for entry in entries] == [1, 2, 10]
    assert [entry.evergreen for entry in entries] == [True, False, False]


def test_parse_evergreen_entries_reads_section_and_legacy_tags():
    content = """# gralph Progress Log

## Evergreen
1. Keep IDs stable.

## Learnings
1. [evergreen] Keep IDs stable.
2. [evergreen] Prefer deterministic snapshots.
3. Added parser regression test.
"""
    entries = parse_evergreen_entries(content)
    assert [entry.text for entry in entries] == [
        "Keep IDs stable.",
        "Prefer deterministic snapshots.",
    ]


def test_append_learning_increments_number_in_learnings(tmp_path):
    progress_path = tmp_path / "progress.txt"
    progress_path.write_text(
        "# gralph Progress Log\n\n## Evergreen\n1. Keep tests fast.\n\n## Learnings\n1. Use uv run.\n2. Add parser tests.\n"
    )

    next_number = append_learning(progress_path, "Added smoke test for CLI")

    assert next_number == 3
    assert "3. Added smoke test for CLI" in progress_path.read_text()


def test_append_learning_evergreen_increments_number_in_evergreen(tmp_path):
    progress_path = tmp_path / "progress.txt"
    progress_path.write_text(
        "# gralph Progress Log\n\n## Evergreen\n1. Keep IDs stable.\n\n## Learnings\n1. Added parser test.\n"
    )

    next_number = append_learning(progress_path, "Prefer deterministic parsing", evergreen=True)

    assert next_number == 2
    content = progress_path.read_text()
    assert "2. Prefer deterministic parsing" in content


def test_append_learning_creates_missing_file_and_sections(tmp_path):
    progress_path = tmp_path / "progress.txt"

    next_number = append_learning(progress_path, "Use stable task ids", evergreen=True)

    assert next_number == 1
    content = progress_path.read_text()
    assert "## Evergreen" in content
    assert "## Learnings" in content
    assert "1. Use stable task ids" in content


def test_append_learning_migrates_legacy_layout_with_evergreen_first(tmp_path):
    progress_path = tmp_path / "progress.txt"
    progress_path.write_text("# gralph Progress Log\n\n## Learnings\n1. Existing note.\n")

    append_learning(progress_path, "[evergreen] Keep tests deterministic.")

    content = progress_path.read_text()
    assert content.index("## Evergreen") < content.index("## Learnings")
    assert "1. Keep tests deterministic." in content


def test_build_memory_snapshot_uses_evergreen_section_and_last_ten_learnings(tmp_path):
    progress_path = tmp_path / "progress.txt"
    evergreen = [
        "1. Keep task ids stable.",
        "2. Use deterministic parsing.",
    ]
    learnings = ["1. One-off note."] + [f"{idx}. Learned item {idx}." for idx in range(2, 12)]
    progress_path.write_text(
        "# gralph Progress Log\n\n## Evergreen\n"
        + "\n".join(evergreen)
        + "\n\n## Learnings\n"
        + "\n".join(learnings)
        + "\n"
    )

    snapshot = build_memory_snapshot(progress_path, recent_limit=10)

    assert "MEMORY SNAPSHOT" in snapshot
    assert "- [1] Keep task ids stable." in snapshot
    assert "- [2] Use deterministic parsing." in snapshot
    assert "- [2] Learned item 2." in snapshot
    assert "- [11] Learned item 11." in snapshot
    assert "- [1] One-off note." not in snapshot
