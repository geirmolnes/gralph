import json

import pytest
from typer.testing import CliRunner

from gralph import cli
from gralph.core.claims import claim_task


def _create_gralph_dir(tmp_path, prd_text: str):
    gralph_dir = tmp_path / ".gralph_planning"
    gralph_dir.mkdir()
    (gralph_dir / "PRD.md").write_text(prd_text)
    return gralph_dir


def test_ready_command_adds_ids_and_lists_ready_tasks(tmp_path, monkeypatch):
    runner = CliRunner()
    gralph_dir = _create_gralph_dir(
        tmp_path,
        "- [ ] Add auth middleware ||| uv run pytest tests/test_auth.py\n",
    )
    monkeypatch.setattr(cli, "find_gralph_dir", lambda: gralph_dir)

    result = runner.invoke(cli.app, ["ready"])
    assert result.exit_code == 0
    assert "Ready Tasks" in result.output
    assert "[id:g-" in (gralph_dir / "PRD.md").read_text()


def test_claim_and_release_commands(tmp_path, monkeypatch):
    runner = CliRunner()
    gralph_dir = _create_gralph_dir(
        tmp_path,
        "- [ ] [id:g-a1b2] Add auth middleware ||| uv run pytest tests/test_auth.py\n",
    )
    monkeypatch.setattr(cli, "find_gralph_dir", lambda: gralph_dir)

    claim_result = runner.invoke(
        cli.app,
        ["claim", "g-a1b2", "--owner", "alice", "--ttl-minutes", "30"],
    )
    assert claim_result.exit_code == 0
    assert "Claimed g-a1b2 as alice for 30m" in claim_result.output

    claims_payload = json.loads((gralph_dir / "claims.json").read_text())
    assert claims_payload["claims"]["g-a1b2"]["owner"] == "alice"

    conflict_result = runner.invoke(
        cli.app,
        ["claim", "g-a1b2", "--owner", "bob"],
    )
    assert conflict_result.exit_code == 1
    assert "already claimed by alice" in conflict_result.output

    release_result = runner.invoke(cli.app, ["release", "g-a1b2", "--force"])
    assert release_result.exit_code == 0
    assert "Released claim for g-a1b2" in release_result.output


@pytest.mark.parametrize(
    ("command", "status"),
    [
        ("done", "x"),
        ("skip", "~"),
        ("fail", "!"),
    ],
)
def test_manual_status_commands_release_claim_and_clear_state(tmp_path, monkeypatch, command, status):
    runner = CliRunner()
    gralph_dir = _create_gralph_dir(
        tmp_path,
        "- [ ] [id:g-a1b2] Add auth middleware ||| uv run pytest tests/test_auth.py\n",
    )
    monkeypatch.setattr(cli, "find_gralph_dir", lambda: gralph_dir)

    claim_task(gralph_dir, "g-a1b2", owner="alice", lease_seconds=3600)
    (gralph_dir / ".ralph_error.txt").write_text("boom")
    (gralph_dir / ".ralph_state.json").write_text('{"current_task":"x"}')

    result = runner.invoke(cli.app, [command, "g-a1b2"])
    assert result.exit_code == 0

    prd_text = (gralph_dir / "PRD.md").read_text()
    assert f"- [{status}] [id:g-a1b2]" in prd_text

    claims_payload = json.loads((gralph_dir / "claims.json").read_text())
    assert claims_payload["claims"] == {}

    assert not (gralph_dir / ".ralph_error.txt").exists()
    assert not (gralph_dir / ".ralph_state.json").exists()
