"""Dependency checking utilities."""

import shutil

REQUIRED_TOOLS = {
    "claude": "Install Claude Code: npm install -g @anthropic-ai/claude-code",
    "docker": "Install Docker: https://docs.docker.com/get-docker/",
    "git": "Install git: https://git-scm.com/downloads",
    "uv": "Install uv: https://docs.astral.sh/uv/getting-started/installation/",
    "bun": "Install bun: https://bun.sh/docs/installation",
}


def check_dependencies() -> list[str]:
    """Check for required external tools and return list of missing ones."""
    missing = []
    for tool, install_hint in REQUIRED_TOOLS.items():
        if not shutil.which(tool):
            missing.append(f"{tool}: {install_hint}")
    return missing
