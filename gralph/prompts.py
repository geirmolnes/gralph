"""Prompt templates for Claude interactions."""

from gralph import GRALPH_DIR

def _sub(template: str) -> str:
    """Replace _PD_ placeholder with the planning directory name."""
    return template.replace("_PD_", GRALPH_DIR)


CLARIFY_PROMPT = """You are a Lead Software Architect gathering requirements. The user wants to build:

Goal: "{goal}"
Stack: {stack}

Ask 3-5 SHORT, SPECIFIC clarifying questions to better understand:
- Key features and scope
- Technical requirements or constraints
- User experience expectations
- Integration needs

FORMAT: Output ONLY numbered questions, one per line. No introduction, no explanation.
Example:
1. Should the CLI support both interactive and non-interactive modes?
2. Do you need to persist data between sessions?
3. What's the expected input format?
"""

ARCHITECT_PROMPT = """You are a Lead Software Architect. I want to build: "{goal}"
Stack: {stack} (use 'uv' for python, 'bun' for javascript).
{clarifications}
Break this down into a list of ATOMIC tasks in logical order.
Each task must have a verifiable check command.

TASK PLANNING:
- Start with project scaffolding: directory structure, entry point, config, dependencies.
- Install dependencies BEFORE tasks that use them.
- Right-size: enough tasks to cover the goal, but don't pad with trivial steps. Each task should represent a meaningful unit of work.
- Keep every task atomic: one clear action and one verification command.

VERIFICATION RULES:
- Prefer `uv run pytest tests/test_X.py` (Python) or `bun test` (JS) for verification.
- Use shell commands (grep, test -f, etc.) only for infra tasks like file creation or dependency installation.
- Verification must be self-contained: no running servers, no network calls, no external services.
- Verification commands must return exit code 0 on success.

CRITICAL FORMAT RULES:
- Output ONLY a markdown checklist. No introduction. No explanation. No code blocks.
- Start your response with "- [ ]" on line 1.
- Each line: - [ ] <description> ||| <verification_command>
- Use EXACTLY ONE ||| separator per line.
- Use ONLY `uv` or `bun` for package management.

Example (Python CLI with database):
- [ ] Initialize project with uv and install typer, sqlite-utils ||| uv pip show typer && uv pip show sqlite-utils
- [ ] Create src/db.py with init_db and connection helper ||| uv run pytest tests/test_db.py
- [ ] Create src/models.py with User dataclass and CRUD functions ||| uv run pytest tests/test_models.py
- [ ] Create src/cli.py with add-user and list-users commands ||| uv run python src/cli.py --help | grep -q "add-user"
- [ ] Add input validation and error handling to CLI commands ||| uv run pytest tests/test_cli.py
- [ ] Add export-csv command that writes users to CSV ||| uv run pytest tests/test_export.py

Example (JS/TS web scraper):
- [ ] Initialize project with bun and install cheerio, node-fetch ||| bun pm ls | grep -q cheerio
- [ ] Create src/fetcher.ts to download page HTML ||| bun test tests/fetcher.test.ts
- [ ] Create src/parser.ts to extract data from HTML ||| bun test tests/parser.test.ts
- [ ] Create src/index.ts CLI entry point combining fetch + parse ||| bun run src/index.ts --help | grep -q "url"
- [ ] Add retry logic and error handling for failed requests ||| bun test tests/fetcher.test.ts
- [ ] Add JSON output format ||| bun test tests/output.test.ts
"""

WORKER_PROMPT_TEMPLATE = _sub("""# gralph Worker Context

## Project Goal
{goal}

## Technology Stack
{stack}

## Package Management
ALWAYS use these tools - never pip, npm, or yarn:
- Python projects: `uv` (uv add, uv run, uv pip, etc.)
- JavaScript/TypeScript: `bun` (bun add, bun run, etc.)
The project is already initialized with the appropriate package manager.

## Directory Structure
CRITICAL: Understand where files live:
- `/workspace/` (or `.`) = PROJECT ROOT - all your code goes here
- `/workspace/_PD_/` = GRALPH CONFIG ONLY - contains PRD.md, PROMPT.md, progress.txt
- `/workspace/tests/` = TEST FILES - all tests go here (pytest for Python, bun test for JS)
- NEVER create project code inside `_PD_/` - that folder is only for gralph metadata

When creating files:
- `src/`, `main.py`, `pyproject.toml`, etc. → project root (`.`)
- Test files → `tests/` (e.g., `tests/test_main.py`)
- Updating task status → `_PD_/PRD.md`
- Logging progress → `_PD_/progress.txt`

## Instructions
You are implementing a project step by step. Focus only on the current task.
Write clean, working code. Make the verification command pass.
Do not modify files unrelated to the current task.
Only when you are truly done, output the completion promise provided in the task context
- Only work on a single task per iteration.
- Update _PD_/PRD.md with progress for that task.
- Append one numbered learning to _PD_/progress.txt.
- Durable/reusable rules go under ## Evergreen. Task-specific notes go under ## Learnings.
- Auth: docker sandbox persists Claude login inside its volume.

## Important
- If you discover something useful, mention it so it can be logged.
- If a task seems impossible, explain why clearly.
- Check existing files before creating new ones.
- Keep both sections as numbered lists only (N. text).
""")

LOOP_PROMPT_TEMPLATE = _sub("""@_PD_/PRD.md @_PD_/PROMPT.md

{memory_snapshot}

DIRECTORY STRUCTURE:
- Project code goes in the ROOT directory (.), NOT inside _PD_/
- _PD_/ folder is ONLY for: PRD.md, PROMPT.md, progress.txt
- tests/ folder is for ALL test files (pytest for Python, bun test for JS)
- Example: create src/main.py at ./src/main.py, tests at ./tests/test_main.py

PACKAGE MANAGEMENT (mandatory):
- Python: ALWAYS use `uv` (uv add, uv run, uv pip) - NEVER use pip directly
- JavaScript: ALWAYS use `bun` (bun add, bun run) - NEVER use npm/yarn

WORKFLOW:
1. Find the highest-priority unchecked task (- [ ]) and implement it.
   - Adopt a TDD approach: create tests in the tests/ directory (e.g., tests/test_feature.py)
   - Run tests with `uv run pytest` (Python) or `bun test` (JS)
   - If TDD is not applicable for the task, you may skip creating a test.
2. Run the verification command for that task.
3. If verification passes, mark the task done: change '- [ ]' to '- [x]' in _PD_/PRD.md.
4. Append exactly one numbered learning to _PD_/progress.txt.
   - Format: N. <learning>
   - Durable/reusable rules must be added to ## Evergreen.
   - Task-specific notes must be added to ## Learnings.
5. Commit your changes with a descriptive message.{push_instruction}
ONLY WORK ON A SINGLE TASK PER ITERATION.
If all tasks are complete (no more '- [ ]'), output: {promise}""")

PUSH_INSTRUCTION = "\n6. Push to remote: git push"

SCAN_PROMPT = """You are a Lead Software Architect analyzing an existing codebase.

Explore the project structure: list files, read key source files, configs, and tests.
Then output EXACTLY two sections:

## Codebase Summary
3-5 lines describing what exists: languages, frameworks, structure, main functionality.

## Suggested Goal
A single paragraph describing what should be built or improved next, based on what you found.
Be specific and actionable. Reference actual files or patterns you observed.
"""

FOLLOW_UP_PROMPT = """You are a Lead Software Architect. A project is in progress.
Stack: {stack} (use 'uv' for python, 'bun' for javascript).

Here is the current PRD with completed tasks:
{prd}

{instruction}

Generate ADDITIONAL tasks to continue the project. Follow the same format and rules as the existing tasks.
Do NOT repeat tasks that are already completed.
Build on what already exists — read the completed tasks to understand the current state.
Before proposing tasks, inspect relevant source files, tests, and configs in the repository.

TASK PLANNING:
- Right-size: each task should represent a meaningful unit of work.
- Keep every task atomic: one clear action and one verification command.

VERIFICATION RULES:
- Prefer `uv run pytest tests/test_X.py` (Python) or `bun test` (JS) for verification.
- Use shell commands only for infra tasks.
- Verification must be self-contained: no running servers, no network calls.
- Verification commands must return exit code 0 on success.

CRITICAL FORMAT RULES:
- Output ONLY a markdown checklist. No introduction. No explanation. No code blocks.
- Start your response with "- [ ]" on line 1.
- Each line: - [ ] <description> ||| <verification_command>
- Use EXACTLY ONE ||| separator per line.
"""

TASK_SELECTION_PROMPT = """You are selecting the next task for implementation.

You must choose the single most important READY task from the candidate list.

Selection priorities (in order):
1. Highest unblocking impact (enables additional pending tasks)
2. Highest risk reduction / correctness
3. Highest direct user value
4. Best sequencing for fast progress

Project PRD:
{prd}

READY TASK CANDIDATES:
{candidates}

Output format rules:
- Output ONLY the task id (example: g-a1b2)
- No explanation
- No markdown
- Must be one of the candidate ids
"""
