# PRD: Improve code in this project

Stack: python

- [x] Review current project structure and main entry point ||| test -f src/gralph/main.py && head -20 src/gralph/main.py | grep -q "def\|import"
- [x] Ensure CLI module is separate from main orchestration ||| test -f src/gralph/cli.py || test -f src/gralph/main.py
- [x] Check if constants are properly centralized ||| grep -r "GRALPH_DIR\|REQUIRED_TOOLS" src/gralph/ | head -1
- [x] Verify templates are in proper location ||| test -d src/gralph/templates || test -f src/gralph/templates.py
- [x] Ensure proper package structure with __init__.py ||| test -f src/gralph/__init__.py
- [ ] Verify pyproject.toml has correct entry point ||| grep -q "scripts\|entry" pyproject.toml
- [ ] Check that imports use relative or proper package imports ||| grep -r "^from gralph\|^import gralph\|^from \." src/gralph/ | head -1
- [ ] Verify the package installs correctly ||| uv pip install -e . && python -c "import gralph"
- [ ] Test CLI runs without errors ||| uv run gralph --help 2>/dev/null || uv run python -m gralph --help