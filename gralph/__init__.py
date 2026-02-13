"""
gralph - Geir's Ralph Loop Scaffolding Tool

Sets up and manages autonomous coding sessions with sandboxed execution.
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("gralph")
except PackageNotFoundError:
    __version__ = "dev"

GRALPH_DIR = ".gralph_planning"
