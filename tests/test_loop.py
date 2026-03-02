from pathlib import Path

from gralph.core import loop as loop_mod


PENDING_PRD = """\
# PRD

Stack: python

- [ ] Build API ||| uv run pytest tests/test_api.py
"""

NO_PENDING_PRD = """\
# PRD

Stack: python

- [x] Build API ||| uv run pytest tests/test_api.py
"""


def _create_gralph_dir(tmp_path: Path, prd_text: str = PENDING_PRD) -> Path:
    gralph_dir = tmp_path / "gralph"
    gralph_dir.mkdir()
    (gralph_dir / "PRD.md").write_text(prd_text)
    return gralph_dir


def _setup_ready_loop(monkeypatch, gralph_dir: Path):
    monkeypatch.setattr(loop_mod, "find_gralph_dir", lambda: gralph_dir)
    monkeypatch.setattr(loop_mod, "ensure_docker_available", lambda: True)
    monkeypatch.setattr(loop_mod, "ensure_image_exists", lambda: True)
    monkeypatch.setattr(loop_mod, "ensure_volume_exists", lambda: True)
    monkeypatch.setattr(loop_mod, "fix_volume_permissions", lambda: True)
    monkeypatch.setattr(loop_mod, "check_container_auth", lambda: True)


def test_run_loop_returns_false_when_not_gralph_project(monkeypatch):
    monkeypatch.setattr(loop_mod, "find_gralph_dir", lambda: None)
    assert loop_mod.run_loop() is False


def test_run_loop_returns_false_when_docker_unavailable(tmp_path: Path, monkeypatch):
    gralph_dir = _create_gralph_dir(tmp_path)
    monkeypatch.setattr(loop_mod, "find_gralph_dir", lambda: gralph_dir)
    monkeypatch.setattr(loop_mod, "ensure_docker_available", lambda: False)
    assert loop_mod.run_loop() is False


def test_run_loop_returns_false_when_auth_missing(tmp_path: Path, monkeypatch):
    gralph_dir = _create_gralph_dir(tmp_path)
    monkeypatch.setattr(loop_mod, "find_gralph_dir", lambda: gralph_dir)
    monkeypatch.setattr(loop_mod, "ensure_docker_available", lambda: True)
    monkeypatch.setattr(loop_mod, "ensure_image_exists", lambda: True)
    monkeypatch.setattr(loop_mod, "ensure_volume_exists", lambda: True)
    monkeypatch.setattr(loop_mod, "fix_volume_permissions", lambda: True)
    monkeypatch.setattr(loop_mod, "check_container_auth", lambda: False)
    assert loop_mod.run_loop() is False


def test_run_loop_fails_fast_when_prd_has_format_errors(tmp_path: Path, monkeypatch):
    broken_prd = """\
# PRD

Stack: python

- [ ] Missing separator
"""
    gralph_dir = _create_gralph_dir(tmp_path, prd_text=broken_prd)
    monkeypatch.setattr(loop_mod, "find_gralph_dir", lambda: gralph_dir)
    monkeypatch.setattr(
        loop_mod,
        "ensure_docker_available",
        lambda: (_ for _ in ()).throw(AssertionError("docker should not run")),
    )

    assert loop_mod.run_loop() is False


def test_run_loop_completes_and_includes_push_instruction(tmp_path: Path, monkeypatch):
    gralph_dir = _create_gralph_dir(tmp_path)
    (gralph_dir / "progress.txt").write_text(
        "# gralph Progress Log\n\n## Evergreen\n"
        "1. Keep IDs stable.\n"
        "\n## Learnings\n"
        "1. Old transient note.\n"
        "2. Learned 2.\n"
        "3. Learned 3.\n"
        "4. Learned 4.\n"
        "5. Learned 5.\n"
        "6. Learned 6.\n"
        "7. Learned 7.\n"
        "8. Learned 8.\n"
        "9. Learned 9.\n"
        "10. Learned 10.\n"
        "11. Learned 11.\n"
    )
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
    assert "@_PD_/progress.txt" not in prompt
    assert "MEMORY SNAPSHOT (_PD_/progress.txt)" in prompt
    assert "- [1] Keep IDs stable." in prompt
    assert "- [1] Old transient note." not in prompt
    assert "- [11] Learned 11." in prompt
    assert promise == "<promise>COMPLETE</promise>"
    assert model == "sonnet"
    assert project_dir == gralph_dir.parent


def test_run_loop_prints_summary_on_completion(tmp_path: Path, monkeypatch):
    gralph_dir = _create_gralph_dir(tmp_path)
    _setup_ready_loop(monkeypatch, gralph_dir)
    monkeypatch.setattr(loop_mod, "stream_claude_docker", lambda *args, **kwargs: (True, "done"))

    printed: list[str] = []
    monkeypatch.setattr(loop_mod.console, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    assert loop_mod.run_loop(max_iterations=3) is True
    assert any("Run Summary" in msg for msg in printed)


def test_run_loop_stops_after_max_iterations(tmp_path: Path, monkeypatch):
    gralph_dir = _create_gralph_dir(tmp_path)
    _setup_ready_loop(monkeypatch, gralph_dir)

    count = {"n": 0}

    def fake_stream(prompt: str, promise: str, model: str, project_dir: Path):
        count["n"] += 1
        return False, "still working"

    monkeypatch.setattr(loop_mod, "stream_claude_docker", fake_stream)

    assert loop_mod.run_loop(max_iterations=2) is False
    assert count["n"] == 2


def test_run_loop_no_pending_returns_true_without_docker(tmp_path: Path, monkeypatch):
    gralph_dir = _create_gralph_dir(tmp_path, prd_text=NO_PENDING_PRD)
    monkeypatch.setattr(loop_mod, "find_gralph_dir", lambda: gralph_dir)
    monkeypatch.setattr(loop_mod, "ensure_docker_available", lambda: (_ for _ in ()).throw(AssertionError("docker should not run")))

    assert loop_mod.run_loop() is True


def test_run_loop_uses_model_selected_ready_task(tmp_path: Path, monkeypatch):
    prd = """\
# PRD

Stack: python

- [ ] [id:g-1111] Add docs ||| test -f README.md
- [ ] [id:g-2222] Add metrics ||| uv run pytest tests/test_metrics.py
"""
    gralph_dir = _create_gralph_dir(tmp_path, prd_text=prd)
    _setup_ready_loop(monkeypatch, gralph_dir)
    monkeypatch.setattr(loop_mod, "select_next_ready_task", lambda *args, **kwargs: ("g-2222", None))

    captured_prompts: list[str] = []

    def fake_stream(prompt: str, promise: str, model: str, project_dir: Path):
        captured_prompts.append(prompt)
        return True, "done"

    monkeypatch.setattr(loop_mod, "stream_claude_docker", fake_stream)

    assert loop_mod.run_loop(max_iterations=1) is True
    assert captured_prompts
    assert "Task ID: g-2222" in captured_prompts[0]
