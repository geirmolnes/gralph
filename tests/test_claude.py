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
