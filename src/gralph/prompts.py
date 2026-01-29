"""Prompt templates for Claude interactions."""

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
Break this down into a list of ATOMIC, SEQUENTIAL tasks.
Each task must have a verifiable check command.

CRITICAL FORMAT RULES:
- Output ONLY a markdown checklist. No introduction. No explanation. No code blocks.
- Start your response with "- [ ]" on line 1.
- Each line: - [ ] <description> ||| <verification_command>
- Use EXACTLY ONE ||| separator per line.
- Verification commands must return exit code 0 on success.
- Use ONLY `uv` or `bun` for package management.

Example output (follow this format exactly):
- [ ] Create main.py with hello world ||| python3 main.py | grep -q "hello"
- [ ] Install requests library ||| uv pip show requests
- [ ] Add CLI argument parsing ||| python3 main.py --help | grep -q "usage"
"""

WORKER_PROMPT_TEMPLATE = """# gralph Worker Context

## Project Goal
{goal}

## Technology Stack
{stack}

## Instructions
You are implementing a project step by step. Focus only on the current task.
Write clean, working code. Make the verification command pass.
Do not modify files unrelated to the current task.
Only when you are truly done, output the completion promise provided in the task context
- Only work on a single task per iteration.
- Update PRD.md with progress for that task.
- Append learnings to progress.txt (patterns at the top).
- Auth: docker sandbox persists Claude login inside its volume.

## Important
- If you discover something useful, mention it so it can be logged.
- If a task seems impossible, explain why clearly.
- Check existing files before creating new ones.
- Log learnings in progress.txt; put reusable patterns in ## Codebase Patterns at the top.
"""

LOOP_PROMPT_TEMPLATE = """@gralph/PRD.md @gralph/progress.txt @gralph/PROMPT.md
1. Find the highest-priority unchecked task (- [ ]) and implement it.
2. Run the verification command for that task.
3. If verification passes, mark the task done: change '- [ ]' to '- [x]' in PRD.md.
4. Append what you learned to progress.txt.
5. Commit your changes with a descriptive message.{push_instruction}
ONLY WORK ON A SINGLE TASK PER ITERATION.
If all tasks are complete (no more '- [ ]'), output: {promise}"""

PUSH_INSTRUCTION = "\n6. Push to remote: git push"
