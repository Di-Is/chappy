"""Utility helpers for building Markdown fragments."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from mdformat import text as _mdformat_text
    from mdformat._exceptions import MdformatError as _MdformatError
except ImportError:  # pragma: no cover - optional dependency
    _mdformat_text = None
    _MdformatError: tuple[type[Exception], ...] = ()
else:
    _MdformatError = (_MdformatError,)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_ALIGN_TOKEN = {"left": ":---", "center": ":---:", "right": "---:", "": "---"}


class MarkdownTableBuilder:
    """Incrementally compose Markdown tables with optional alignment."""

    def __init__(
        self,
        headers: Sequence[str],
        *,
        alignments: Sequence[str] | None = None,
        empty_placeholder: str = "―",
    ) -> None:
        if not headers:
            msg = "MarkdownTableBuilder requires at least one header."
            raise ValueError(msg)
        self._headers = list(headers)
        self._alignments = list(alignments or [""] * len(headers))
        if len(self._alignments) != len(self._headers):
            msg = "alignments length must match headers length."
            raise ValueError(msg)
        self._empty_placeholder = empty_placeholder
        header_line = "| " + " | ".join(self._headers) + " |"
        divider = "| " + " | ".join(_ALIGN_TOKEN.get(a, "---") for a in self._alignments) + " |"
        self._lines: list[str] = [header_line, divider]

    def add_row(self, values: Sequence[str]) -> None:
        """Append a single row to the table."""
        if len(values) != len(self._headers):
            msg = "Row length must match number of headers."
            raise ValueError(msg)
        row = [
            value if value not in ("", None) else self._empty_placeholder  # type: ignore[arg-type]
            for value in values
        ]
        self._lines.append("| " + " | ".join(row) + " |")

    def extend(self, rows: Iterable[Sequence[str]]) -> None:
        """Append multiple rows."""
        for row in rows:
            self.add_row(row)

    def lines(self, *, leading_blank: bool = True) -> list[str]:
        """Return the accumulated lines, optionally prefixed with a blank line.

        Markdown renderers expect a blank line between preceding content (for example, images
        or headings) and a table. By default we insert that separator to avoid rendering quirks.
        Set `leading_blank=False` to retrieve only the raw table lines.
        """
        lines = list(self._lines)
        if leading_blank and lines and lines[0] != "":
            return ["", *lines]
        return lines

    def as_text(self) -> str:
        """Return the table as a Markdown string."""
        return "\n".join(self.lines())


def format_markdown_text(content: str) -> str:
    """Format Markdown content using mdformat when available."""
    if _mdformat_text is None:
        return content
    try:
        formatted = _mdformat_text(content)
    except _MdformatError:  # pragma: no cover - mdformat failure fallback
        return content
    return formatted
