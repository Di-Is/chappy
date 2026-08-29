"""Helpers for loading and rendering Markdown templates."""

from __future__ import annotations

from importlib import resources
from typing import Protocol

_TEMPLATE_PACKAGE = "chappy_user_manual_generator.template_data"


def load_markdown_template(name: str) -> str:
    """Return the raw text for a named Markdown template."""
    template_path = resources.files(_TEMPLATE_PACKAGE).joinpath(name)
    return template_path.read_text(encoding="utf-8")


class SupportsFormat(Protocol):
    """Protocol for values that can be rendered via :func:`str.format`."""

    def __format__(self, format_spec: str) -> str:
        """Produce a formatted string representation."""
        ...


def render_markdown_template(name: str, **context: SupportsFormat) -> str:
    """Render a Markdown template with the provided context."""
    template = load_markdown_template(name)
    return template.format(**context)
