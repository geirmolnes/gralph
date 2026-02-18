"""Claude Code interaction."""

import re
import subprocess

from gralph.prompts import (
    INTERVIEW_START_PROMPT,
    INTERVIEW_FOLLOWUP_PROMPT,
    EPIC_PROMPT,
    EXPAND_PROMPT,
    ARCHITECT_PROMPT_FLAT,
    COMPLEXITY_RANGES,
)


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
    """Generate follow-up tasks based on current PRD state."""
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
    """Ask Claude to pick the most important task id from the ready set."""
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


# ---------- Interview functions ----------

def get_interview_questions(
    goal: str,
    stack: str,
    conversation_so_far: str = "",
) -> tuple[str | None, bool, str | None]:
    """Run one round of the interview loop.

    Returns (text, is_done, error).
    - If is_done=True, text is the DONE: summary block.
    - Otherwise text is follow-up questions.
    """
    if not conversation_so_far:
        prompt = INTERVIEW_START_PROMPT.format(goal=goal, stack=stack)
    else:
        prompt = INTERVIEW_FOLLOWUP_PROMPT.format(
            goal=goal, stack=stack, conversation=conversation_so_far,
        )

    raw, error = _run_claude_print(prompt, timeout=120)
    if error or raw is None:
        return None, False, error

    if raw.strip().startswith("DONE:"):
        return raw.strip(), True, None

    return raw.strip(), False, None


def parse_interview_summary(raw: str) -> tuple[str, str]:
    """Extract structured summary and complexity from DONE: output.

    Returns (summary_text, complexity) where complexity is S/M/L/XL.
    """
    complexity = "M"  # default
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("complexity:"):
            val = stripped.split(":", 1)[1].strip().upper()
            if val and val[0] in {"S", "M", "L", "X"}:
                complexity = "XL" if val.startswith("XL") else val[0]

    # The full DONE: block is the summary (minus the DONE: prefix)
    summary = raw
    if summary.startswith("DONE:"):
        summary = summary[5:].strip()

    return summary, complexity


# ---------- Epic generation ----------

def generate_epics(
    goal: str,
    stack: str,
    interview_summary: str,
    complexity: str = "M",
) -> tuple[str | None, str | None]:
    """Generate high-level epics. Returns (epics_markdown, error)."""
    ranges = COMPLEXITY_RANGES.get(complexity, COMPLEXITY_RANGES["M"])
    lo, hi = ranges["epics"]
    epic_range = f"{lo}-{hi}"

    prompt = EPIC_PROMPT.format(
        goal=goal,
        stack=stack,
        interview_summary=interview_summary or "(no additional context)",
        complexity=complexity,
        epic_range=epic_range,
    )

    raw, error = _run_claude_print(prompt, timeout=120)
    if error or raw is None:
        return None, error

    # Strip markdown code fences
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(line for line in lines if not line.startswith("```"))

    return raw.strip(), None


def parse_epics(epics_text: str) -> list[dict[str, str]]:
    """Parse epic markdown into list of {name, description}."""
    epics: list[dict[str, str]] = []
    current_name = ""
    current_lines: list[str] = []

    for line in epics_text.splitlines():
        header_match = re.match(r"^##\s+\d+\.\s+(.+)$", line.strip())
        if header_match:
            if current_name:
                epics.append({
                    "name": current_name,
                    "description": "\n".join(current_lines).strip(),
                })
            current_name = header_match.group(1).strip()
            current_lines = []
        elif current_name:
            current_lines.append(line)

    if current_name:
        epics.append({
            "name": current_name,
            "description": "\n".join(current_lines).strip(),
        })

    return epics


def expand_epic(
    goal: str,
    stack: str,
    epic: dict[str, str],
    all_epics_text: str,
    task_target: int,
) -> tuple[str | None, str | None]:
    """Expand a single epic into atomic tasks. Returns (task_lines, error)."""
    prompt = EXPAND_PROMPT.format(
        goal=goal,
        stack=stack,
        all_epics=all_epics_text,
        task_target=task_target,
        epic_name=epic["name"],
        epic_description=epic["description"],
    )

    raw, error = _run_claude_print(prompt, timeout=180)
    if error or raw is None:
        return None, error

    # Strip markdown code fences
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(line for line in lines if not line.startswith("```"))

    return raw.strip(), None


# ---------- Flat single-shot (--quick fallback) ----------

def generate_prd_flat(
    goal: str,
    stack: str,
    clarifications: str = "",
) -> tuple[str | None, str | None]:
    """Generate a flat PRD in one shot (--quick mode)."""
    clarification_text = f"\nAdditional context:\n{clarifications}\n" if clarifications else ""
    prompt = ARCHITECT_PROMPT_FLAT.format(goal=goal, stack=stack, clarifications=clarification_text)
    ai_prd, error = _run_claude_print(prompt, timeout=180)
    if error or ai_prd is None:
        return None, error

    if ai_prd.startswith("```"):
        lines = ai_prd.split("\n")
        ai_prd = "\n".join(line for line in lines if not line.startswith("```"))

    return ai_prd, None
