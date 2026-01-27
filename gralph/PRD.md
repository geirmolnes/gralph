# PRD: Improve code in this project

Stack: python

- [x] Add constants to module top (move GRALPH_DIR near other constants) ||| grep -q "^GRALPH_DIR = " gralph.py && grep -q "^REQUIRED_TOOLS = " gralph.py
- [x] Extract RALPH_SH to external file gralph/templates/ralph.sh ||| test -f templates/ralph.sh && python3 -c "from gralph import RALPH_SH" 2>&1 | grep -q "cannot import"
- [ ] Replace try/except ImportError with proper dependency check ||| python3 -c "import gralph" 2>&1 | grep -qv "Missing dependencies"
- [ ] Add return type hints to all functions ||| grep -E "^def " gralph.py | grep -v " -> " | wc -l | grep -q "^0$"
- [ ] Extract PRD validation logic to separate module validators.py ||| test -f validators.py && python3 -c "from validators import validate_prd"
- [ ] Extract file operations to utils.py module ||| test -f utils.py && python3 -c "from utils import find_gralph_dir"
- [ ] Add error handling enum for consistent exit codes ||| grep -q "class ExitCode" gralph.py || grep -q "class ExitCode" utils.py
- [ ] Sync version in pyproject.toml with __version__ in gralph.py ||| python3 -c "import tomllib; from gralph import __version__; t=tomllib.load(open('pyproject.toml','rb')); assert t['project']['version']==__version__"
- [ ] Add CLI test for bootstrap command ||| uv run pytest tests/test_cli.py -k "bootstrap" -q
- [ ] Add CLI test for status command ||| uv run pytest tests/test_cli.py -k "status" -q