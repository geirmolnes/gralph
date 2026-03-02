"""Path utilities for gralph."""

from pathlib import Path

from gralph import GRALPH_DIR

_GRALPH_README = """\
# gralph/

Managed by [gralph](https://github.com/geirmolnes/gralph).

## Files

| File | Purpose |
|---|---|
| PRD.md | Task list. `- [ ] description \\|\\|\\| verification_command` |
| progress.txt | Learnings carried between iterations |
| claims.json | Multi-agent claim coordination (auto-managed) |

## Task format

`[ ]` pending · `[x]` done · `[~]` skipped · `[!]` failed
Dependencies: `[deps:g-xxxx]` · IDs: `[id:g-xxxx]` (auto-assigned)
"""


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


def ensure_gralph_dir() -> Path:
    """Create gralph/ dir with README if missing. Moves root PRD.md in if needed."""
    gralph_path = Path.cwd() / GRALPH_DIR
    gralph_path.mkdir(exist_ok=True)

    # Move PRD.md from project root into gralph/ if not already there
    root_prd = Path.cwd() / "PRD.md"
    target_prd = gralph_path / "PRD.md"
    if root_prd.exists() and not target_prd.exists():
        root_prd.rename(target_prd)

    readme = gralph_path / "README.md"
    if not readme.exists():
        readme.write_text(_GRALPH_README)
    return gralph_path
