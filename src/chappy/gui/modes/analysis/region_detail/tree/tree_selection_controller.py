"""Controller for optimize tree selection workflow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import Qt

from chappy.core.absorption.models import AbsorptionLine
from chappy.core.components.absorber import AbsorberComponent

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem


class OptimizeTreeSelectionPort(Protocol):
    """Panel operations required by tree selection workflow."""

    def clear_selected_line(self) -> None:
        """Clear selected line state and dependent UI."""
        ...

    def select_line_from_tree(self, line: AbsorptionLine, component_id: str | None) -> None:
        """Apply selected line state and dependent UI."""
        ...


class OptimizeTreeSelectionController:
    """Coordinate optimize tree selection changes."""

    def __init__(self, *, tree: QTreeWidget, port: OptimizeTreeSelectionPort) -> None:
        """Initialize the controller.

        Args:
            tree: Tree widget that owns optimize rows.
            port: Panel-facing selection operations.
        """
        self._tree = tree
        self._port = port

    def selection_changed(self) -> None:
        """Handle selection changes in the optimize model tree."""
        selected_items = self._tree.selectedItems()
        if not selected_items:
            self._port.clear_selected_line()
            return

        item = self._effective_item(selected_items)
        line = self._line_for_item(item)
        if line is None:
            self._port.clear_selected_line()
            return

        self._port.select_line_from_tree(line, self._component_id_for_item(item))

    def _effective_item(self, selected_items: list[QTreeWidgetItem]) -> QTreeWidgetItem:
        """Return the current item when selected, otherwise the first selection."""
        current_item = self._tree.currentItem()
        if current_item is None or not current_item.isSelected():
            return selected_items[0]
        return current_item

    @staticmethod
    def _component_id_for_item(item: QTreeWidgetItem) -> str | None:
        """Return the absorber component id of a child row, or ``None`` for a line row."""
        if item.parent() is None:
            return None
        component = item.data(0, Qt.ItemDataRole.UserRole)
        return component.id if isinstance(component, AbsorberComponent) else None

    def _line_for_item(self, item: QTreeWidgetItem) -> AbsorptionLine | None:
        """Return line data stored on a line item or model item parent."""
        line_item = item if item.parent() is None else item.parent()
        line_data = line_item.data(0, Qt.ItemDataRole.UserRole)
        return line_data if isinstance(line_data, AbsorptionLine) else None
