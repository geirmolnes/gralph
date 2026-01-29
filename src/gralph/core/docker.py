"""Docker sandboxed execution for Claude."""

import json
import os
import shutil
import subprocess
from pathlib import Path

from gralph.utils.console import console


DOCKERFILE_CONTENT = """\
FROM node:20-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    python3 \\
    python3-pip \\
    python3-venv \\
    git \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Use existing node user (UID 1000), create .claude dir
RUN mkdir -p /home/node/.claude && chown -R node:node /home/node/.claude

USER node
WORKDIR /workspace

ENTRYPOINT ["claude"]
"""

CLAUDE_HOME = "/home/node/.claude"

VOLUME_NAME = "gralph-claude-config"


def ensure_docker_available() -> bool:
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def ensure_image_exists(image_name: str = "gralph-sandbox") -> bool:
    """Build the Docker image if it doesn't exist."""
    # Check if image exists
    result = subprocess.run(
        ["docker", "images", "-q", image_name],
        capture_output=True,
        text=True,
    )
    
    if result.stdout.strip():
        return True
    
    console.print(f"[yellow]Building Docker image '{image_name}'...[/yellow]")
    
    # Build image from Dockerfile content
    process = subprocess.Popen(
        ["docker", "build", "-t", image_name, "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    
    stdout, _ = process.communicate(input=DOCKERFILE_CONTENT)
    
    if process.returncode != 0:
        console.print(f"[red]Failed to build Docker image:[/red]\n{stdout}")
        return False
    
    console.print(f"[green]Docker image '{image_name}' built successfully[/green]")
    return True


def ensure_volume_exists() -> bool:
    """Create Docker volume for Claude config if it doesn't exist."""
    result = subprocess.run(
        ["docker", "volume", "inspect", VOLUME_NAME],
        capture_output=True,
    )
    
    if result.returncode == 0:
        return True
    
    # Create volume
    result = subprocess.run(
        ["docker", "volume", "create", VOLUME_NAME],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        console.print(f"[red]Failed to create Docker volume:[/red]\n{result.stderr}")
        return False
    
    console.print(f"[dim]Created Docker volume '{VOLUME_NAME}'[/dim]")
    return True


def check_container_auth(image_name: str = "gralph-sandbox") -> bool:
    """Check if Claude is authenticated inside the container."""
    # Run a minimal prompt to test auth
    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{VOLUME_NAME}:{CLAUDE_HOME}",
            image_name,
            "-p", "--print", "say ok",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    # Check for auth errors
    output = result.stdout + result.stderr
    if "Invalid API key" in output or "Please run /login" in output:
        return False
    return result.returncode == 0


def fix_volume_permissions(image_name: str = "gralph-sandbox") -> None:
    """Ensure volume has correct permissions for non-root user."""
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{VOLUME_NAME}:{CLAUDE_HOME}",
            "--user", "root",
            "--entrypoint", "chown",
            image_name,
            "-R", "1000:1000", CLAUDE_HOME,
        ],
        capture_output=True,
    )


def authenticate_container(image_name: str = "gralph-sandbox") -> bool:
    """Run interactive Claude session to trigger login flow."""
    # Fix permissions before starting
    fix_volume_permissions(image_name)
    
    console.print("[cyan]Starting Claude in Docker container...[/cyan]")
    console.print("[dim]If prompted, complete the login flow in your browser.[/dim]")
    console.print("[dim]Type 'exit' or Ctrl+C when done.[/dim]\n")
    
    result = subprocess.run(
        [
            "docker", "run", "--rm", "-it",
            "-v", f"{VOLUME_NAME}:{CLAUDE_HOME}",
            image_name,
        ],
    )
    
    # Check if auth worked after the session
    return check_container_auth(image_name)


def get_claude_config_dir() -> Path:
    """Get Claude Code config directory."""
    # Claude Code stores config in ~/.claude
    return Path.home() / ".claude"


def stream_claude_docker(
    prompt: str,
    completion_promise: str,
    model: str = "sonnet",
    project_dir: Path = None,
    image_name: str = "gralph-sandbox",
) -> tuple[bool, str]:
    """
    Run Claude inside Docker with streaming output.
    
    Args:
        prompt: The prompt to send to Claude
        completion_promise: Token that signals task completion
        model: Claude model to use
        project_dir: Project directory to mount (defaults to cwd)
        image_name: Docker image name
    
    Returns:
        Tuple of (completed, full_output) where completed is True if promise was found.
    """
    if project_dir is None:
        project_dir = Path.cwd()
    
    # Build docker run command
    cmd = [
        "docker", "run",
        "--rm",
        "-i",
        # Mount project directory
        "-v", f"{project_dir.absolute()}:/workspace",
        # Mount Claude config volume (read-write for session data)
        "-v", f"{VOLUME_NAME}:{CLAUDE_HOME}",
        # Set working directory
        "-w", "/workspace",
        # Image
        image_name,
        # Claude args
        "-p",
        "--dangerously-skip-permissions",
        "--output-format=stream-json",
        "--verbose",
        "--model", model,
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
                    console.print()  # Newline after assistant message
                
                elif event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        console.print(text, end="", highlight=False)
                        full_output.append(text)
                        if completion_promise in text:
                            found_promise = True
                
                elif event_type == "content_block_stop":
                    # End of a content block - add newline for readability
                    console.print()
                
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
                        console.print(f"\n[dim]{msg}[/dim]")
                
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
        if process.returncode != 0:
            stderr = process.stderr.read() if process.stderr else ""
            if stderr:
                console.print(f"[red]Docker error: {stderr[:500]}[/red]")
    
    return found_promise, "".join(full_output)
