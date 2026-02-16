"""Claude Code interaction."""

import re
import subprocess


def _run_claude_print(prompt: str, timeout: int = 180) -> tuple[str | None, str | None]:
    """Run `claude --print` with consistent error handling."""
    cmd = ["claude", "--print", prompt]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return None, "Claude CLI not found in PATH. Install: npm install -g @anthropic-ai/claude-code"
    except subprocess.TimeoutExpired:
        return None, f"Claude request timed out after {timeout}s"
    except OSError as exc:
        return None, f"Failed to run Claude CLI: {exc}"

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "Unknown error").strip()
        return None, err[:500]

    return result.stdout.strip(), None


def scan_codebase(scan_prompt: str) -> tuple[str | None, str | None]:
    """Run Claude with scan prompt to analyze existing codebase."""
    return _run_claude_print(scan_prompt, timeout=120)


def generate_follow_up_tasks(prd_text: str, stack: str, prompt_template: str, user_instruction: str = "") -> tuple[str | None, str | None]:
    """Generate follow-up tasks based on current PRD state and optional user input."""
    if user_instruction:
        instruction = f"The user wants to continue with:\n{user_instruction}"
    else:
        instruction = (
            "Scan the current codebase and recent completed tasks in the PRD, then suggest "
            "logical next steps: improvements, tests, documentation, edge cases, or features "
            "that would make this more complete."
        )

    prompt = prompt_template.format(prd=prd_text, stack=stack, instruction=instruction)
    tasks, error = _run_claude_print(prompt, timeout=180)
    if error or tasks is None:
        return None, error

    if tasks.startswith("```"):
        lines = tasks.split("\n")
        tasks = "\n".join(line for line in lines if not line.startswith("```"))

    return tasks, None


def select_next_ready_task(
    prd_text: str,
    ready_tasks: list[dict[str, str]],
    selection_prompt: str,
) -> tuple[str | None, str | None]:
    """
    Ask Claude to pick the most important task id from the ready set.

    Returns:
        (task_id, error). Exactly one is None.
    """
    if not ready_tasks:
        return None, "No ready tasks to select from."

    candidate_ids = {t.get("task_id", "").strip() for t in ready_tasks if t.get("task_id")}
    if not candidate_ids:
        return None, "Ready tasks are missing task IDs."

    candidates = "\n".join(
        (
            f"- {task['task_id']}: {task['description']} ||| {task['verification']}"
            if not task.get("deps")
            else f"- {task['task_id']}: {task['description']} [deps: {task['deps']}] ||| {task['verification']}"
        )
        for task in ready_tasks
    )

    prompt = selection_prompt.format(prd=prd_text, candidates=candidates)
    picked, error = _run_claude_print(prompt, timeout=90)
    if error or not picked:
        return None, error

    first_line = picked.strip().splitlines()[0].strip().strip("`")
    if first_line in candidate_ids:
        return first_line, None

    for candidate in candidate_ids:
        if re.search(rf"\b{re.escape(candidate)}\b", picked):
            return candidate, None

    return None, f"Model returned invalid task id: {first_line}"


def get_clarifying_questions(goal: str, stack: str, clarify_prompt: str) -> tuple[str | None, str | None]:
    """
    Get clarifying questions from Claude.
    
    Returns:
        Tuple of (questions, error_message). One will be None.
    """
    prompt = clarify_prompt.format(goal=goal, stack=stack)
    return _run_claude_print(prompt, timeout=120)


def generate_prd(goal: str, stack: str, architect_prompt: str, clarifications: str = "") -> tuple[str | None, str | None]:
    """
    Generate a PRD using Claude.
    
    Args:
        goal: Project goal
        stack: Technology stack
        architect_prompt: The architect prompt template
        clarifications: Additional context from clarifying Q&A
    
    Returns:
        Tuple of (prd_content, error_message). One will be None.
    """
    clarification_text = f"\nAdditional context:\n{clarifications}\n" if clarifications else ""
    prompt = architect_prompt.format(goal=goal, stack=stack, clarifications=clarification_text)
    ai_prd, error = _run_claude_print(prompt, timeout=180)
    if error or ai_prd is None:
        return None, error
    
    # Strip markdown code blocks if present
    if ai_prd.startswith("```"):
        lines = ai_prd.split("\n")
        ai_prd = "\n".join(line for line in lines if not line.startswith("```"))
    
    return ai_prd, None
