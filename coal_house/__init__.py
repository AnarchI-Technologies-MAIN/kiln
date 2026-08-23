"""Packaged coal-house resources for language-agnostic Kiln adapters."""

from pathlib import Path


def coal_house_root() -> Path:
    """Return the installed or source-tree coal-house resource root."""
    return Path(__file__).resolve().parent

