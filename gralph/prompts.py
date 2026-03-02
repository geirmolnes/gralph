"""Prompt templates for Claude interactions."""

from gralph import GRALPH_DIR

def _sub(template: str) -> str:
    """Replace _PD_ placeholder with the planning directory name."""
    return template.replace("_PD_", GRALPH_DIR)


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

TEAM_PROMPT_TEMPLATE = _sub("""You are the lead agent for a gralph team session.

## Your Task
- Task ID: {task_id}
- Description: {description}
- Verification command: {verification}

## Project Context
{prompt_md}

{memory_snapshot}

## Directory Structure
- `/workspace/` (or `.`) = PROJECT ROOT — all project code goes here
- `/workspace/_PD_/` = GRALPH CONFIG — PRD.md, PROMPT.md, progress.txt
- `/workspace/tests/` = TEST FILES

## Package Management
- Python: ALWAYS use `uv` (uv add, uv run, uv pip) — NEVER pip
- JavaScript: ALWAYS use `bun` (bun add, bun run) — NEVER npm/yarn

## Team Setup
Create an agent team to implement this task. ALWAYS spawn these two roles:

1. **implementer** — Writes the code changes for the task. Uses TDD where applicable.
2. **tester** — Writes tests, runs the verification command, validates correctness.

If the task warrants it (security-sensitive, complex logic, DB migrations, API design, performance-critical), spawn a 3rd specialist agent with an appropriate role. Simple tasks should use only 2 agents.

## Coordination Flow
1. Implementer writes the code
2. Tester writes tests and runs verification command: `{verification}`
3. If a specialist is present, they review their domain concern
4. Fix any issues found
5. When verification passes, update _PD_/PRD.md: change `- [ ]` to `- [x]` for task {task_id}
6. Append one numbered learning to _PD_/progress.txt under ## Learnings
7. Commit changes with a descriptive message

## Important
- Only work on task {task_id} — do not touch other tasks
- Check existing files before creating new ones
- Keep project code in the root, NOT inside _PD_/
""")
