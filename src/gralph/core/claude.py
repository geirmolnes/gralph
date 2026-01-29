"""Claude Code interaction and streaming."""

import json
import subprocess

from gralph.utils.console import console


def stream_claude_output(
    prompt: str, completion_promise: str, model: str = "sonnet"
) -> tuple[bool, str]:
    """
    Run Claude with streaming JSON output and display in real-time.
    
    Args:
        prompt: The prompt to send to Claude
        completion_promise: Token that signals task completion
        model: Claude model to use
    
    Returns:
        Tuple of (completed, full_output) where completed is True if promise was found.
    """
    cmd = [
        "claude",
        "-p",
        "--dangerously-skip-permissions",
        "--output-format=stream-json",
        "--verbose",
        "--model",
        model,
    ]
    
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    
    process.stdin.write(prompt)
    process.stdin.close()
    
    full_output = []
    found_promise = False
    
    try:
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            
            try:
                event = json.loads(line)
                event_type = event.get("type", "")
                
                if event_type == "assistant":
                    content = event.get("message", {}).get("content", [])
                    for block in content:
                        if block.get("type") == "text":
                            text = block.get("text", "")
                            console.print(text, end="")
                            full_output.append(text)
                            if completion_promise in text:
                                found_promise = True
                
                elif event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        console.print(text, end="", highlight=False)
                        full_output.append(text)
                        if completion_promise in text:
                            found_promise = True
                
                elif event_type == "result":
                    result_text = event.get("result", "")
                    if result_text and completion_promise in result_text:
                        found_promise = True
                
                elif event_type == "error":
                    error_msg = event.get("error", {}).get("message", "Unknown error")
                    console.print(f"\n[red]Error: {error_msg}[/red]")
                
                elif event_type == "system":
                    msg = event.get("message", "")
                    if msg:
                        console.print(f"[dim]{msg}[/dim]")
                
            except json.JSONDecodeError:
                console.print(line)
                full_output.append(line)
                if completion_promise in line:
                    found_promise = True
        
        console.print()
        
    except KeyboardInterrupt:
        process.terminate()
        raise
    finally:
        process.wait()
        # Check for errors
        if process.returncode != 0:
            stderr = process.stderr.read() if process.stderr else ""
            if stderr:
                console.print(f"[red]Claude error: {stderr[:500]}[/red]")
    
    return found_promise, "".join(full_output)


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
