"""Claude Code interaction."""

import subprocess


def generate_follow_up_tasks(prd_text: str, stack: str, prompt_template: str, user_instruction: str = "") -> tuple[str | None, str | None]:
    """Generate follow-up tasks based on current PRD state and optional user input."""
    if user_instruction:
        instruction = f"The user wants to continue with:\n{user_instruction}"
    else:
        instruction = "Review the project state and suggest logical next steps: improvements, tests, documentation, edge cases, or features that would make this more complete."

    prompt = prompt_template.format(prd=prd_text, stack=stack, instruction=instruction)
    cmd = ["claude", "--print", prompt]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        return None, result.stderr[:500] if result.stderr else "Unknown error"

    tasks = result.stdout.strip()
    if tasks.startswith("```"):
        lines = tasks.split("\n")
        tasks = "\n".join(line for line in lines if not line.startswith("```"))

    return tasks, None


def get_clarifying_questions(goal: str, stack: str, clarify_prompt: str) -> tuple[str | None, str | None]:
    """
    Get clarifying questions from Claude.
    
    Returns:
        Tuple of (questions, error_message). One will be None.
    """
    prompt = clarify_prompt.format(goal=goal, stack=stack)
    cmd = ["claude", "--print", prompt]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        return None, result.stderr[:500] if result.stderr else "Unknown error"
    
    return result.stdout.strip(), None


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
    cmd = ["claude", "--print", prompt]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        return None, result.stderr[:500] if result.stderr else "Unknown error"
    
    ai_prd = result.stdout.strip()
    
    # Strip markdown code blocks if present
    if ai_prd.startswith("```"):
        lines = ai_prd.split("\n")
        ai_prd = "\n".join(line for line in lines if not line.startswith("```"))
    
    return ai_prd, None
