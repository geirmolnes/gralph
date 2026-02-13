import subprocess

from typer.testing import CliRunner

from gralph import cli


class _Result:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_docker_run(args, **kwargs):
    if args[:2] == ["docker", "info"]:
        return _Result(returncode=0)
    if args[:3] == ["docker", "images", "-q"]:
        return _Result(returncode=0, stdout="img123\n")
    return _Result(returncode=0)


def test_doctor_fails_when_uv_missing(monkeypatch):
    runner = CliRunner()

    which_map = {
        "claude": "/usr/bin/claude",
        "docker": "/usr/bin/docker",
        "git": "/usr/bin/git",
        "uv": None,
        "bun": "/usr/bin/bun",
    }

    monkeypatch.setattr(cli.shutil, "which", lambda tool: which_map.get(tool))
    monkeypatch.setattr(cli.subprocess, "run", _fake_docker_run)

    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 1
    assert "uv: NOT FOUND" in result.output


def test_doctor_succeeds_when_all_tools_are_present(monkeypatch):
    runner = CliRunner()

    which_map = {
        "claude": "/usr/bin/claude",
        "docker": "/usr/bin/docker",
        "git": "/usr/bin/git",
        "uv": "/usr/bin/uv",
        "bun": "/usr/bin/bun",
    }

    monkeypatch.setattr(cli.shutil, "which", lambda tool: which_map.get(tool))
    monkeypatch.setattr(cli.subprocess, "run", _fake_docker_run)

    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0
    assert "All dependencies satisfied!" in result.output


def test_doctor_fails_when_docker_health_check_times_out(monkeypatch):
    runner = CliRunner()

    which_map = {
        "claude": "/usr/bin/claude",
        "docker": "/usr/bin/docker",
        "git": "/usr/bin/git",
        "uv": "/usr/bin/uv",
        "bun": "/usr/bin/bun",
    }

    def fake_run(args, **kwargs):
        if args[:2] == ["docker", "info"]:
            raise subprocess.TimeoutExpired(cmd=args, timeout=15)
        return _Result(returncode=0)

    monkeypatch.setattr(cli.shutil, "which", lambda tool: which_map.get(tool))
    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 1
    assert "Docker health check failed" in result.output
