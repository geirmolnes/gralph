# gralph 🍩

Autonomous "Ralph Wiggum" dev loop for project scaffolding and task execution. Drives AI agents through iterative cycles of planning, coding, and verification — sandboxed via Docker for secure YOLO mode autonomy.

## How It Works

1. **Bootstrap** - Describe what you want to build, answer clarifying questions
2. **Plan** - Claude generates an atomic task list with verification commands
3. **Loop** - Each iteration: fresh Docker container → implement one task → verify → commit
4. **Complete** - All tasks checked off, project built

The "Ralph loop" pattern: stateless iterations with state persisted to files. Claude has no memory between iterations — only what's in `PRD.md`, `progress.txt`, and `PROMPT.md`.

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

## Commands

| Command | Description |
|---------|-------------|
| `gralph init <name>` | Create new project directory and initialize |
| `gralph bootstrap` | Initialize gralph in current directory |
| `gralph auth` | Authenticate Claude inside Docker container |
| `gralph run` | Run the Ralph loop |
| `gralph status` | Show task progress |
| `gralph skip` | Skip current task |
| `gralph done` | Manually mark current task complete |
| `gralph edit` | Open PRD in editor |
| `gralph log <msg>` | Add note to progress log |
| `gralph reset` | Reset all tasks to pending |
| `gralph doctor` | Check dependencies |

## Options

### `gralph init` / `gralph bootstrap`
- `-g, --goal` — What to build
- `-s, --stack` — Tech stack (default: python)
- `-q, --quick` — Skip clarifying questions

### `gralph run`
- `-m, --max` — Max iterations (default: 20)
- `--model` — Claude model (default: sonnet)
- `--push` — Push to remote after each commit

## Project Structure

After bootstrapping, gralph creates:

```
your-project/
├── gralph/
│   ├── PRD.md        # Task checklist with verification commands
│   ├── PROMPT.md     # Context for Claude worker
│   ├── progress.txt  # Learnings log
│   └── ralph.sh      # Standalone loop runner
└── ... your code
```

### PRD Format

Each task has a description and verification command:

```markdown
- [ ] Create main.py with hello world ||| python3 main.py | grep -q "hello"
- [ ] Add CLI argument parsing ||| python3 main.py --help | grep -q "usage"
- [x] Install requests library ||| uv pip show requests
```

## Docker Sandbox

All code execution happens inside a Docker container with:
- Python 3, Git, Node.js pre-installed
- Project directory mounted at `/workspace`
- Claude auth persisted in a Docker volume
- No access to host system outside project directory

## License

MIT
