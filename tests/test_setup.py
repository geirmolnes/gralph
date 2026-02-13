from pathlib import Path

from gralph.core import setup as setup_mod


class _Completed:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_stack_detection_does_not_misclassify_typescript_cli():
    assert setup_mod.is_python_stack("typescript cli") is False
    assert setup_mod.is_js_stack("typescript cli") is True


def test_init_package_manager_prefers_bun_for_node_cli(tmp_path: Path, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return _Completed()

    monkeypatch.setattr(setup_mod.subprocess, "run", fake_run)

    setup_mod.init_package_manager("node cli", tmp_path)

    assert calls[0] == ["bun", "init", "-y"]
    assert (tmp_path / "tests").is_dir()
    assert not (tmp_path / "tests" / "__init__.py").exists()


def test_init_package_manager_skips_mixed_stack(tmp_path: Path, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return _Completed()

    monkeypatch.setattr(setup_mod.subprocess, "run", fake_run)

    setup_mod.init_package_manager("python and node", tmp_path)

    assert calls == []
