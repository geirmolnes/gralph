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
