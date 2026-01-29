"""Path utilities for gralph."""

from pathlib import Path

from gralph import GRALPH_DIR


def find_gralph_dir() -> Path | None:
    """Find the gralph directory in current or parent directories, stopping at git root."""
    current = Path.cwd()
    for _ in range(10):
        gralph_path = current / GRALPH_DIR
        if gralph_path.is_dir() and (gralph_path / "PRD.md").exists():
            return gralph_path
        # Stop at git root
        if (current / ".git").exists():
            break
        if current.parent == current:
            break
        current = current.parent
    return None
