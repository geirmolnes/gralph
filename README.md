# gralph

Focused task runner for autonomous coding loops. Drives AI agents through iterative cycles of coding and verification — sandboxed via Docker.

## How It Works

1. **You** create `gralph/PRD.md` with a task checklist (or use any external tool to generate it)
2. **Loop** — Each iteration: fresh Docker container → implement one task → verify → commit
3. **Complete** — Loop exits with a run summary

The "Ralph loop" pattern: stateless iterations with state persisted to files. Claude has no memory between iterations — it sees `PRD.md`, `PROMPT.md`, and a deterministic snapshot from `progress.txt`.

## Installation

```bash
uv tool install git+https://github.com/geirmolnes/gralph.git

# Or clone and install locally
git clone https://github.com/geirmolnes/gralph.git
cd gralph
uv tool install .
```

**Requirements:**
- Docker (for sandboxed execution)
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)

## Quick Start

```bash
# Create gralph/PRD.md with your tasks (see format below)
mkdir gralph
cat > gralph/PRD.md << 'EOF'
# PRD

Stack: python

- [ ] Initialize project with uv and install typer ||| uv pip show typer
- [ ] Create src/main.py with CLI entrypoint ||| uv run python src/main.py --help
EOF

# Run the loop
gralph run
```

## Commands

| Command | Description |
|---------|-------------|
| `gralph run [max]` | Run the Ralph loop (default: 20 iterations) |
| `gralph team [max]` | Run the loop with Claude agent teams enabled |
| `gralph status` | Show task progress counts |
| `gralph tasks` | List all tasks with color-coded statuses |
| `gralph ready` | Show runnable tasks (deps satisfied + unclaimed) |

### `gralph run`
- `--model` — Claude model (default: sonnet)
- `--push` — Push to remote after each commit
- `--owner` — Claim owner identity for this run

### `gralph team`
Same options as `run`. Enables Claude agent teams (multiple sub-agents per task).

## Project Structure

```
your-project/
├── gralph/
│   ├── PRD.md        # Task checklist with verification commands
│   ├── PROMPT.md     # Context for Claude worker (optional)
│   ├── progress.txt  # Numbered memory sections (Evergreen + Learnings)
│   └── claims.json   # Active task claims with lease expiry (auto-managed)
├── tests/
└── ... your code
```

The `gralph/` directory is auto-created with a README on first `run` or `team` if missing.

### PRD Format

```markdown
# PRD

Stack: python

## Setup & Infrastructure
- [ ] [id:g-a1b2] Initialize project with uv, install rich and typer ||| uv pip show typer
- [ ] [id:g-c3d4] Create project directory structure ||| test -d src && test -d tests

## Data Layer
- [ ] [id:g-e5f6] [deps:g-a1b2] Create src/db.py with SQLite helper ||| uv run pytest tests/test_db.py
- [x] [id:g-g7h8] Install requests library ||| uv pip show requests
```

- `[id:...]` — stable task identity (auto-assigned if missing)
- `[deps:task1,task2]` — blocks execution until dependencies are completed/skipped/failed
- `[ ]` pending · `[x]` done · `[~]` skipped · `[!]` failed

### Progress Memory

`progress.txt` uses two numbered sections:

```markdown
## Evergreen
1. Keep task verifications self-contained.

## Learnings
1. Added metrics endpoint test fixtures.
```

- `## Evergreen` — durable rules (always included in prompt)
- `## Learnings` — task notes (last 10 included in prompt)

## Docker Sandbox

All code execution happens inside a Docker container with:
- Python 3, Git, Node.js pre-installed
- Project directory mounted at `/workspace`
- Claude auth persisted in a Docker volume

## License

MIT
