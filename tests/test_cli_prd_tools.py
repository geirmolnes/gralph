from typer.testing import CliRunner

from gralph import cli


def _create_gralph_dir(tmp_path, prd_text: str):
    gralph_dir = tmp_path / ".gralph_planning"
    gralph_dir.mkdir()
    (gralph_dir / "PRD.md").write_text(prd_text)
    return gralph_dir


def test_lint_prd_command_reports_errors(tmp_path, monkeypatch):
    runner = CliRunner()
    gralph_dir = _create_gralph_dir(
        tmp_path,
        "- [ ] Missing separator\n",
    )
    monkeypatch.setattr(cli, "find_gralph_dir", lambda: gralph_dir)

    result = runner.invoke(cli.app, ["lint-prd"])

    assert result.exit_code == 1
    assert "PRD format issues found" in result.output
    assert "Missing |||" in result.output


def test_fix_prd_command_normalizes_and_makes_lint_pass(tmp_path, monkeypatch):
    runner = CliRunner()
    gralph_dir = _create_gralph_dir(
        tmp_path,
        "- [X]   Build auth   |||    pytest tests/test_auth.py\n",
    )
    monkeypatch.setattr(cli, "find_gralph_dir", lambda: gralph_dir)

    result = runner.invoke(cli.app, ["fix-prd"])
    assert result.exit_code == 0
    assert "Applied 1 PRD formatting fix" in result.output

    lint_result = runner.invoke(cli.app, ["lint-prd"])
    assert lint_result.exit_code == 0
    assert "PRD format looks good" in lint_result.output
