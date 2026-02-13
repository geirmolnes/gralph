"""Rich console setup and display helpers."""

import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from gralph import __version__

console = Console()


def show_version():
    """Display version banner."""
    console.print(f"[bold cyan]gralph[/bold cyan] v{__version__}")


def prompt_input(
    question: str,
    hint: str = "",
    default: str = "",
    required: bool = True,
) -> str:
    """Prompt for input with a Claude-Code-style panel above the cursor.

    Shows a bordered box with the question and hint text, then a ``>``
    prompt underneath for the user to type into.
    """
    # Build panel content
    lines = f"[bold]{question}[/bold]"
    if hint:
        lines += f"\n[dim]{hint}[/dim]"

    console.print()
    console.print(
        Panel(
            lines,
            border_style="cyan",
            padding=(1, 2),
        )
    )

    # Non-interactive (piped stdin) – require value via flags
    if not sys.stdin.isatty():
        if default:
            return default
        console.print(f"[red]Cannot prompt in non-interactive mode. Pass the value via flags.[/red]")
        raise SystemExit(1)

    while True:
        if default:
            value = Prompt.ask("  [bold cyan]>[/bold cyan]", default=default)
        else:
            value = Prompt.ask("  [bold cyan]>[/bold cyan]")

        value = value.strip()
        if value or not required:
            # Echo back long input in a wrapped panel so the user can
            # verify what was captured (pasted text is hard to read raw).
            if value and len(value) > 60:
                console.print(
                    Panel(
                        value,
                        border_style="dim",
                        padding=(0, 2),
                        expand=False,
                    )
                )
            return value

        console.print("  [dim]Please enter a value.[/dim]")
