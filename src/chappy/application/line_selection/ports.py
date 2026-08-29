"""Ports required by line selection use cases."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from chappy.core.atomic_data import AtomicLine


@runtime_checkable
class MultipletCatalogPort(Protocol):
    """Minimal atomic-line catalog needed for selection set operations."""

    def get_lines_by_multiplet(self, multiplet_id: str) -> list[AtomicLine]:
        """Return every line belonging to the given multiplet."""
        ...

    def get_line_by_id(self, line_id: str) -> AtomicLine | None:
        """Return the line for an identifier, or ``None`` when unknown."""
        ...
