from pathlib import Path

from gralph.core import loop as loop_mod


def _setup_ready_loop(monkeypatch, gralph_dir: Path):
    monkeypatch.setattr(loop_mod, "find_gralph_dir", lambda: gralph_dir)
    monkeypatch.setattr(loop_mod, "ensure_docker_available", lambda: True)
    monkeypatch.setattr(loop_mod, "ensure_image_exists", lambda: True)
    monkeypatch.setattr(loop_mod, "ensure_volume_exists", lambda: True)
    monkeypatch.setattr(loop_mod, "fix_volume_permissions", lambda: True)
    monkeypatch.setattr(loop_mod, "check_container_auth", lambda: True)
    monkeypatch.setattr(loop_mod, "_prompt_next_action", lambda _: False)


def test_run_loop_returns_false_when_not_gralph_project(monkeypatch):
    monkeypatch.setattr(loop_mod, "find_gralph_dir", lambda: None)
    assert loop_mod.run_loop() is False


def test_run_loop_returns_false_when_docker_unavailable(tmp_path: Path, monkeypatch):
    gralph_dir = tmp_path / ".gralph_planning"
    gralph_dir.mkdir()
    monkeypatch.setattr(loop_mod, "find_gralph_dir", lambda: gralph_dir)
    monkeypatch.setattr(loop_mod, "ensure_docker_available", lambda: False)
    assert loop_mod.run_loop() is False


def test_run_loop_returns_false_when_auth_missing(tmp_path: Path, monkeypatch):
    gralph_dir = tmp_path / ".gralph_planning"
    gralph_dir.mkdir()
    monkeypatch.setattr(loop_mod, "find_gralph_dir", lambda: gralph_dir)
    monkeypatch.setattr(loop_mod, "ensure_docker_available", lambda: True)
    monkeypatch.setattr(loop_mod, "ensure_image_exists", lambda: True)
    monkeypatch.setattr(loop_mod, "ensure_volume_exists", lambda: True)
    monkeypatch.setattr(loop_mod, "fix_volume_permissions", lambda: True)
    monkeypatch.setattr(loop_mod, "check_container_auth", lambda: False)
    assert loop_mod.run_loop() is False


def test_run_loop_completes_and_includes_push_instruction(tmp_path: Path, monkeypatch):
    gralph_dir = tmp_path / ".gralph_planning"
    gralph_dir.mkdir()
    _setup_ready_loop(monkeypatch, gralph_dir)

    calls: list[tuple[str, str, str, Path]] = []

    def fake_stream(prompt: str, promise: str, model: str, project_dir: Path):
        calls.append((prompt, promise, model, project_dir))
        return True, f"done {promise}"

    monkeypatch.setattr(loop_mod, "stream_claude_docker", fake_stream)

    assert loop_mod.run_loop(max_iterations=3, push=True) is True
    assert len(calls) == 1
    prompt, promise, model, project_dir = calls[0]
    assert "6. Push to remote: git push" in prompt
    assert promise == "<promise>COMPLETE</promise>"
    assert model == "sonnet"
    assert project_dir == gralph_dir.parent


def test_run_loop_stops_after_max_iterations(tmp_path: Path, monkeypatch):
    gralph_dir = tmp_path / ".gralph_planning"
    gralph_dir.mkdir()
    _setup_ready_loop(monkeypatch, gralph_dir)

    count = {"n": 0}

    def fake_stream(prompt: str, promise: str, model: str, project_dir: Path):
        count["n"] += 1
        return False, "still working"

    monkeypatch.setattr(loop_mod, "stream_claude_docker", fake_stream)

    assert loop_mod.run_loop(max_iterations=2) is False
    assert count["n"] == 2
