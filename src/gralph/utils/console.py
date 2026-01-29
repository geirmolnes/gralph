"""Rich console setup and display helpers."""

from rich.console import Console

from gralph import __version__

console = Console()


def show_version():
    """Display version banner."""
    console.print(f"[bold cyan]gralph[/bold cyan] v{__version__}")
