"""Dependency checking utilities."""

import shutil

REQUIRED_TOOLS = {
    "docker": "Install Docker: https://docs.docker.com/get-docker/",
}


def check_dependencies() -> list[str]:
    """Check for required external tools and return list of missing ones."""
    missing = []
    for tool, install_hint in REQUIRED_TOOLS.items():
        if not shutil.which(tool):
            missing.append(f"{tool}: {install_hint}")
    return missing
