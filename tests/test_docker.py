import json
import subprocess
from pathlib import Path

from gralph.core import docker


class _FakeStdin:
    def __init__(self):
        self.buffer = ""
        self.closed = False

    def write(self, text: str):
        self.buffer += text

    def close(self):
        self.closed = True


class _FakeProcess:
    def __init__(self, lines: list[str], returncode: int = 0):
        self.stdin = _FakeStdin()
        self.stdout = iter(lines)
        self.returncode = returncode

    def wait(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15


def test_stream_claude_docker_uses_combined_streams_and_finds_promise(monkeypatch):
    captured_kwargs = {}

    lines = [
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "hello"}]},
            }
        )
        + "\n",
        json.dumps({"type": "content_block_delta", "delta": {"type": "text_delta", "text": " world"}})
        + "\n",
        json.dumps({"type": "result", "result": "<promise>COMPLETE</promise>"}) + "\n",
    ]

    def fake_popen(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return _FakeProcess(lines, returncode=0)

    monkeypatch.setattr(docker.subprocess, "Popen", fake_popen)

    completed, output = docker.stream_claude_docker(
        prompt="do work",
        completion_promise="<promise>COMPLETE</promise>",
        project_dir=Path("."),
    )

    assert captured_kwargs["stderr"] == subprocess.STDOUT
    assert completed is True
    assert "hello" in output
    assert "<promise>COMPLETE</promise>" in output


def test_stream_claude_docker_returns_error_output_on_nonzero(monkeypatch):
    lines = ["plain error line\n"]

    def fake_popen(*args, **kwargs):
        return _FakeProcess(lines, returncode=2)

    monkeypatch.setattr(docker.subprocess, "Popen", fake_popen)

    completed, output = docker.stream_claude_docker(
        prompt="do work",
        completion_promise="<promise>COMPLETE</promise>",
        project_dir=Path("."),
    )

    assert completed is False
    assert "plain error line" in output
