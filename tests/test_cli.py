import typer
from typer.testing import CliRunner

from gralph import cli


def test_edit_supports_editor_args(tmp_path, monkeypatch):
    gralph_dir = tmp_path / ".gralph_planning"
    gralph_dir.mkdir()
    (gralph_dir / "PRD.md").write_text("- [ ] Task ||| test -f x\n")

    calls: list[list[str]] = []

    class _Result:
        returncode = 0

    def fake_run(args, **kwargs):
        calls.append(args)
        return _Result()

    monkeypatch.setattr(cli, "find_gralph_dir", lambda: gralph_dir)
    monkeypatch.setattr(cli.os, "environ", {"EDITOR": "code --wait"})
    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    cli.edit("prd")

    assert calls == [["code", "--wait", str(gralph_dir / "PRD.md")]]


def test_edit_raises_if_editor_not_found(tmp_path, monkeypatch):
    gralph_dir = tmp_path / ".gralph_planning"
    gralph_dir.mkdir()
    (gralph_dir / "PRD.md").write_text("- [ ] Task ||| test -f x\n")

    def fake_run(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(cli, "find_gralph_dir", lambda: gralph_dir)
    monkeypatch.setattr(cli.os, "environ", {"EDITOR": "missing-editor"})
    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    try:
        cli.edit("prd")
        assert False, "Expected typer.Exit"
    except typer.Exit as exc:
        assert exc.exit_code == 1


def test_log_appends_numbered_learning(tmp_path, monkeypatch):
    runner = CliRunner()
    gralph_dir = tmp_path / ".gralph_planning"
    gralph_dir.mkdir()
    (gralph_dir / "progress.txt").write_text(
        "# gralph Progress Log\n\n## Evergreen\n1. Stable rule.\n\n## Learnings\n1. Existing learning.\n"
    )
    monkeypatch.setattr(cli, "find_gralph_dir", lambda: gralph_dir)

    result = runner.invoke(cli.app, ["log", "Added deterministic parser"])

    assert result.exit_code == 0
    assert "✏️  Logged." in result.output
    assert "2. Added deterministic parser" in (gralph_dir / "progress.txt").read_text()
