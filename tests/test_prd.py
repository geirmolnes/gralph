from pathlib import Path

from gralph.core.prd import (
    append_tasks,
    count_tasks,
    fix_prd_format,
    lint_prd,
    mark_task,
    parse_current_task,
    reset_all_tasks,
    validate_prd,
)

VALID_PRD = """\
# Project
- [ ] Build auth ||| pytest tests/test_auth.py
- [ ] Build API ||| pytest tests/test_api.py
"""

NO_SEP_PRD = """\
- [ ] Build auth without separator
"""

EMPTY_VERIFY_PRD = """\
- [ ] Build auth |||
"""

NO_TASKS_PRD = """\
# Just a header
Some description
"""

ALL_DONE_PRD = """\
- [x] Build auth ||| pytest tests/test_auth.py
- [~] Build API ||| pytest tests/test_api.py
"""

MIXED_PRD = """\
- [x] Done task ||| pytest tests/t1.py
- [~] Skipped task ||| pytest tests/t2.py
- [!] Failed task ||| pytest tests/t3.py
- [ ] Pending task ||| pytest tests/t4.py
- [ ] Another pending ||| pytest tests/t5.py
"""

BROKEN_PRD = """\
- [X] Uppercase status ||| pytest tests/test_upper.py
- [ ] Missing separator
- [ ]  ||| pytest tests/test_empty_desc.py
- [ ] Has verify but empty |||
"""

NEEDS_FIX_PRD = """\
- [X]   Build auth   |||    pytest tests/test_auth.py
- [ ]Build API|||pytest tests/test_api.py
"""


class TestValidatePrd:
    def test_valid(self):
        valid, errors = validate_prd(VALID_PRD)
        assert valid is True
        assert errors == []

    def test_missing_separator(self):
        valid, errors = validate_prd(NO_SEP_PRD)
        assert valid is False
        assert any("Missing |||" in e for e in errors)

    def test_empty_verification(self):
        valid, errors = validate_prd(EMPTY_VERIFY_PRD)
        assert valid is False
        assert any("Empty verification" in e for e in errors)

    def test_no_tasks(self):
        valid, errors = validate_prd(NO_TASKS_PRD)
        assert valid is False
        assert any("No tasks found" in e for e in errors)


class TestLintPrd:
    def test_returns_line_level_errors(self):
        errors = lint_prd(BROKEN_PRD)
        assert any("Line 1" in e and "lowercase 'x'" in e for e in errors)
        assert any("Line 2" in e and "Missing |||" in e for e in errors)
        assert any("Line 3" in e and "Empty task description" in e for e in errors)
        assert any("Line 4" in e and "Empty verification" in e for e in errors)

    def test_no_errors_for_valid_prd(self):
        assert lint_prd(VALID_PRD) == []


class TestFixPrdFormat:
    def test_normalizes_common_spacing_and_status(self):
        fixed, fixes = fix_prd_format(NEEDS_FIX_PRD)
        assert fixes == 2
        assert "- [x] Build auth ||| pytest tests/test_auth.py" in fixed
        assert "- [ ] Build API ||| pytest tests/test_api.py" in fixed

    def test_does_not_change_unfixable_lines(self):
        fixed, fixes = fix_prd_format(NO_SEP_PRD)
        assert fixes == 0
        assert fixed == NO_SEP_PRD


class TestParseCurrentTask:
    def test_finds_first_unchecked(self):
        assert parse_current_task(MIXED_PRD) == "Pending task"

    def test_returns_none_when_all_done(self):
        assert parse_current_task(ALL_DONE_PRD) is None


class TestCountTasks:
    def test_mixed_statuses(self):
        counts = count_tasks(MIXED_PRD)
        assert counts == {
            "completed": 1,
            "skipped": 1,
            "failed": 1,
            "pending": 2,
        }


class TestMarkTask:
    def _write_prd(self, tmp_path: Path, text: str) -> Path:
        p = tmp_path / "PRD.md"
        p.write_text(text)
        return p

    def test_marks_first_pending(self, tmp_path):
        p = self._write_prd(tmp_path, VALID_PRD)
        result = mark_task(p, "x")
        assert result == "Build auth"
        content = p.read_text()
        assert "- [x] Build auth" in content
        assert "- [ ] Build API" in content

    def test_returns_none_when_no_pending(self, tmp_path):
        p = self._write_prd(tmp_path, ALL_DONE_PRD)
        assert mark_task(p, "x") is None


class TestAppendTasks:
    def test_appends_valid_tasks(self, tmp_path):
        p = tmp_path / "PRD.md"
        p.write_text(ALL_DONE_PRD)
        new = "- [ ] Add logging ||| uv run pytest tests/test_log.py\n- [ ] Add config ||| uv run pytest tests/test_config.py"
        count = append_tasks(p, new)
        assert count == 2
        content = p.read_text()
        assert "- [ ] Add logging" in content
        assert "- [ ] Add config" in content

    def test_filters_non_task_lines(self, tmp_path):
        p = tmp_path / "PRD.md"
        p.write_text(ALL_DONE_PRD)
        new = "Here are some tasks:\n- [ ] Real task ||| test -f foo\nSome explanation"
        count = append_tasks(p, new)
        assert count == 1
        content = p.read_text()
        assert "- [ ] Real task" in content
        assert "Some explanation" not in content

    def test_returns_zero_for_empty(self, tmp_path):
        p = tmp_path / "PRD.md"
        p.write_text(ALL_DONE_PRD)
        assert append_tasks(p, "no tasks here") == 0


class TestResetAllTasks:
    def test_resets_all_statuses(self, tmp_path):
        p = tmp_path / "PRD.md"
        p.write_text(MIXED_PRD)
        reset_all_tasks(p)
        content = p.read_text()
        assert content.count("- [ ]") == 5
        assert "- [x]" not in content
        assert "- [~]" not in content
        assert "- [!]" not in content
