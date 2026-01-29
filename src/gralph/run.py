#!/usr/bin/env python3
"""
Standalone Ralph loop runner.

Can be run directly: python -m gralph.run
Or as a script: ./run.py
"""

import argparse
import sys

from gralph.core.loop import run_loop
from gralph.utils.console import show_version


def main():
    parser = argparse.ArgumentParser(
        description="Run the Ralph loop in Docker sandbox"
    )
    parser.add_argument(
        "-m", "--max",
        type=int,
        default=20,
        help="Maximum iterations (default: 20)"
    )
    parser.add_argument(
        "-p", "--promise",
        default="<promise>COMPLETE</promise>",
        help="Completion promise token"
    )
    parser.add_argument(
        "--model",
        default="sonnet",
        help="Claude model to use (default: sonnet)"
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push to remote after each commit"
    )
    parser.add_argument(
        "-v", "--version",
        action="store_true",
        help="Show version and exit"
    )
    
    args = parser.parse_args()
    
    if args.version:
        show_version()
        sys.exit(0)
    
    show_version()
    success = run_loop(
        max_iterations=args.max,
        completion_promise=args.promise,
        model=args.model,
        push=args.push,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
