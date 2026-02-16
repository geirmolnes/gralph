# gralph 🍩

Autonomous "Ralph Wiggum" dev loop for project scaffolding and task execution. Drives AI agents through iterative cycles of planning, coding, and verification — sandboxed via Docker for secure YOLO mode autonomy.

## How It Works

1. **Bootstrap** - Describe what you want to build, answer clarifying questions
2. **Plan** - Claude generates an atomic task list with verification commands
3. **Loop** - Each iteration: fresh Docker container → implement one task → verify → commit
4. **Complete** - Loop exits with a run summary (iterations + task deltas)

The "Ralph loop" pattern: stateless iterations with state persisted to files. Claude has no memory between iterations — it sees `PRD.md`, `PROMPT.md`, and a deterministic snapshot from `progress.txt` (all entries in `## Evergreen` + last 10 entries in `## Learnings`).

## Installation

```bash
# Install with uv
uv tool install git+https://github.com/geirmolnes/gralph.git

# Or clone and install locally
git clone https://github.com/geirmolnes/gralph.git
cd gralph
uv tool install .
```

**Requirements:**
- Docker (for sandboxed execution)
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- `uv` (for Python projects) — [install](https://docs.astral.sh/uv/getting-started/installation/)
- `bun` (for JS/TS projects) — [install](https://bun.sh/docs/installation)

## Quick Start

```bash
# Authenticate Claude in Docker sandbox (one-time)
gralph auth

# Create a new project
gralph init myproject -g "CLI tool that converts CSV to JSON" -s python

# Or bootstrap in existing directory
cd existing-project
gralph bootstrap -g "add REST API" -s python

# Run the loop
cd myproject
gralph run
```

If there are no pending tasks at run start, `gralph run` offers to generate suggested follow-up tasks (with an option to cancel).

## Commands

| Command | Description |
|---------|-------------|
| `gralph init <name>` | Create new project directory and initialize |
| `gralph bootstrap` | Initialize gralph in current directory |
| `gralph auth` | Authenticate Claude inside Docker container |
| `gralph run [max]` | Run the Ralph loop (default: 20 iterations) |
| `gralph ready` | Show runnable tasks (deps satisfied + unclaimed) |
| `gralph claim <id>` | Claim a task with a lease for multi-agent safety |
| `gralph release <id>` | Release an active claim |
| `gralph stale` | List/prune expired claims |
| `gralph status` | Show task progress counts |
| `gralph tasks` | List all tasks with color-coded statuses |
| `gralph done` | Manually mark current task complete |
| `gralph skip` | Skip current task |
| `gralph fail` | Mark current task as failed |
| `gralph edit [file]` | Open planning file in editor (`prd`, `prompt`, `progress`) |
| `gralph lint-prd` | Validate PRD task formatting and show line-level errors |
| `gralph fix-prd` | Auto-fix common PRD formatting drift |
| `gralph log <msg>` | Add numbered learning to progress log |
| `gralph progress` | View the progress log |
| `gralph reset` | Reset all tasks to pending |
| `gralph rebuild` | Force rebuild of Docker sandbox image |
| `gralph doctor` | Check dependencies |

## Options

### `gralph init` / `gralph bootstrap`
- `-g, --goal` — What to build
- `-s, --stack` — Tech stack (default: python)
- `-q, --quick` — Skip clarifying questions
- `--goal-file` — Path to a text/markdown file with project context

### `gralph run`
- `--model` — Claude model (default: sonnet)
- `--push` — Push to remote after each commit
- `--owner` — Claim owner identity for this run

### Run Behavior
- `gralph run` is non-interactive while tasks are executing.
- Before each iteration, gralph computes ready tasks from PRD dependencies and active task claims.
- If multiple tasks are ready, gralph asks the model to prioritize the highest-impact task.
- If run starts with no pending tasks, gralph can suggest new tasks from the current PRD and codebase context.
- After task completion, run exits and prints a summary (iterations, task deltas, current totals).

### PRD Hygiene
- `gralph lint-prd` shows task-format issues with line numbers.
- `gralph fix-prd` normalizes common formatting drift (checkbox casing and separator spacing).
- `gralph run` validates PRD format before execution and fails fast with guidance if formatting is invalid.

## Project Structure

After bootstrapping, gralph creates:

```
your-project/
├── .gralph_planning/
│   ├── PRD.md        # Task checklist with verification commands
│   ├── PROMPT.md     # Context for Claude worker
│   ├── progress.txt  # Numbered memory sections (Evergreen + Learnings)
│   └── claims.json   # Active task claims with lease expiry
├── tests/            # Test directory (auto-created)
├── pyproject.toml    # Python: auto-initialized with uv
└── ... your code
```

### Auto-Initialization

Based on your stack, gralph automatically:
- **Python**: Runs `uv init`, adds `pytest` as dev dependency, creates `tests/`
- **JavaScript/TypeScript**: Runs `bun init`, creates `tests/`

This ensures the project is ready to go before Claude starts working.

### PRD Format

Each task has a description and verification command:

```markdown
- [ ] Create main.py with hello world ||| python3 main.py | grep -q "hello"
- [ ] Add CLI argument parsing ||| python3 main.py --help | grep -q "usage"
- [x] Install requests library ||| uv pip show requests
```

Optional metadata tags can be included in descriptions:

```markdown
- [ ] [id:g-a1b2] Build auth middleware [deps:g-91ff] ||| uv run pytest tests/test_auth.py
```

- `[id:...]` provides a stable task identity for claim/release operations.
- `[deps:task1,task2]` blocks task execution until dependencies are completed/skipped/failed.

### Progress Memory Format

`progress.txt` should use two numbered sections:

```markdown
## Evergreen
1. Keep task verifications self-contained.
2. Prefer deterministic parsing over heuristic parsing.

## Learnings
1. Added metrics endpoint test fixtures.
2. Simplified PRD parser edge-case handling.
3. Replaced note blocks with numbered entries.
```

- Put durable/reusable rules in `## Evergreen`.
- Put task/run notes in `## Learnings`.
- `gralph run` ingests all `## Evergreen` entries plus only the last 10 `## Learnings` entries.
- Legacy `[evergreen]` tags in `## Learnings` are still recognized during transition.

## Docker Sandbox

All code execution happens inside a Docker container with:
- Python 3, Git, Node.js pre-installed
- Project directory mounted at `/workspace`
- Claude auth persisted in a Docker volume
- No access to host system outside project directory

## License

MIT
