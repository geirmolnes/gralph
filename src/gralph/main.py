"""Main entry point and orchestration for gralph.

This module provides the main function that orchestrates the gralph workflow.
It can be called from CLI or used programmatically.
"""

import sys
from typing import Optional

from gralph.core.loop import run_loop
from gralph.core.setup import core_setup
from gralph.utils.console import console, show_version


def main(
    command: str = "run",
    max_iterations: int = 20,
    completion_promise: str = "<promise>COMPLETE</promise>",
    model: str = "sonnet",
    goal: Optional[str] = None,
    stack: Optional[str] = "python",
    skip_clarify: bool = False,
) -> bool:
    """Main orchestration function for gralph.

    Args:
        command: Command to run (setup, run)
        max_iterations: Maximum iterations for run loop
        completion_promise: Completion promise token
        model: Claude model to use
        goal: Project goal for setup
        stack: Tech stack for setup
        skip_clarify: Skip clarifying questions in setup

    Returns:
        True if successful, False otherwise
    """
    show_version()

    if command == "setup":
        return core_setup(goal, stack, skip_clarify=skip_clarify)
    elif command == "run":
        return run_loop(max_iterations, completion_promise, model)
    else:
        console.print(f"[red]Unknown command: {command}[/red]")
        return False


if __name__ == "__main__":
    # Simple CLI when run directly
    import argparse

    parser = argparse.ArgumentParser(description="gralph - Ralph loop scaffolding")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["setup", "run"],
        help="Command to execute"
    )
    parser.add_argument("-m", "--max", type=int, default=20, help="Max iterations")
    parser.add_argument("--model", default="sonnet", help="Claude model")
    parser.add_argument("-g", "--goal", help="Project goal (for setup)")
    parser.add_argument("-s", "--stack", default="python", help="Tech stack (for setup)")
    parser.add_argument("-q", "--quick", action="store_true", help="Skip clarifying questions")

    args = parser.parse_args()

    success = main(
        command=args.command,
        max_iterations=args.max,
        model=args.model,
        goal=args.goal,
        stack=args.stack,
        skip_clarify=args.quick,
    )

    sys.exit(0 if success else 1)
