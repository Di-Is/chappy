"""Shared table item helpers for identify side panel tables."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem


class SortableNumericItem(QTableWidgetItem):
    """Table item that sorts numerically using a stored value."""

    def __init__(self, display: str, sort_value: float) -> None:
        """Store a formatted string and its numeric sort key."""
        super().__init__(display)
        self._sort_value = sort_value

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Compare numeric sort keys when Qt requests ordering."""
        if isinstance(other, SortableNumericItem):
            return self._sort_value < other._sort_value

        other_value: float | None = None
        if other is not None:
            data = other.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, int | float):
                other_value = float(data)
            else:
                try:
                    other_value = float(other.text())
                except (TypeError, ValueError):
                    other_value = None

        if other_value is not None:
            return self._sort_value < other_value
        return super().__lt__(other)
