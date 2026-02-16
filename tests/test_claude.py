import subprocess

from gralph.core import claude


class _Completed:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_scan_codebase_handles_missing_claude(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(claude.subprocess, "run", fake_run)

    output, error = claude.scan_codebase("scan")
    assert output is None
    assert "Claude CLI not found" in error


def test_generate_prd_handles_timeout(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["claude"], timeout=180)

    monkeypatch.setattr(claude.subprocess, "run", fake_run)

    output, error = claude.generate_prd("goal", "python", "{goal} {stack} {clarifications}")
    assert output is None
    assert error == "Claude request timed out after 180s"


def test_generate_follow_up_tasks_strips_code_fences(monkeypatch):
    def fake_run(*args, **kwargs):
        return _Completed(stdout="```markdown\n- [ ] Task ||| test -f x\n```")

    monkeypatch.setattr(claude.subprocess, "run", fake_run)

    tasks, error = claude.generate_follow_up_tasks(
        "current",
        "python",
        "{prd}\n{stack}\n{instruction}",
    )
    assert error is None
    assert tasks == "- [ ] Task ||| test -f x"


def test_select_next_ready_task_returns_valid_id(monkeypatch):
    def fake_run(*args, **kwargs):
        return _Completed(stdout="g-a1b2")

    monkeypatch.setattr(claude.subprocess, "run", fake_run)

    task_id, error = claude.select_next_ready_task(
        prd_text="# PRD",
        ready_tasks=[
            {
                "task_id": "g-a1b2",
                "description": "Add auth",
                "verification": "uv run pytest tests/test_auth.py",
                "deps": "",
            },
            {
                "task_id": "g-c3d4",
                "description": "Add docs",
                "verification": "uv run pytest tests/test_docs.py",
                "deps": "",
            },
        ],
        selection_prompt="{prd}\n{candidates}",
    )

    assert error is None
    assert task_id == "g-a1b2"
