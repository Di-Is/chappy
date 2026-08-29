"""QTreeWidget adapter for optimize mode tree view operations."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import TYPE_CHECKING

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from chappy.core.absorption.models import AbsorptionLine
from chappy.core.components.absorber import AbsorberComponent
from chappy.gui.modes.analysis.region_detail.tree.tree_columns import (
    COL_ANALYSIS_HALF_WIDTH,
    COL_SPECIES,
    ROLE_LINE_IDS,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from types import TracebackType

    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.analysis.region_detail.tree.tree_row_renderer import (
        OptimizeTreeRowRenderer,
    )


class OptimizeTreeViewAdapter:
    """Encapsulate concrete QTreeWidget traversal and selection operations."""

    def __init__(
        self,
        *,
        tree: QTreeWidget,
        row_renderer: OptimizeTreeRowRenderer,
        set_item_changed_suppressed: Callable[[bool], None],
        on_selection_changed: Callable[[], None],
    ) -> None:
        """Initialize the adapter.

        Args:
            tree: Optimize parameter tree widget.
            row_renderer: Renderer used for component and group rows.
            set_item_changed_suppressed: Callback toggling item-changed suppression.
            on_selection_changed: Callback invoked after programmatic line selection.
        """
        self._tree = tree
        self._row_renderer = row_renderer
        self._set_item_changed_suppressed = set_item_changed_suppressed
        self._on_selection_changed = on_selection_changed

    def clear(self) -> None:
        """Clear all rows from the tree."""
        self._tree.clear()

    def iter_component_rows(self) -> Iterable[tuple[QTreeWidgetItem, AbsorberComponent]]:
        """Yield rendered component rows and their stored component references."""
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent_item = root.child(i)
            for j in range(parent_item.childCount()):
                child_item = parent_item.child(j)
                component = child_item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(component, AbsorberComponent):
                    yield child_item, component

    def iter_model_items(self) -> Iterable[QTreeWidgetItem]:
        """Yield all rendered component row items."""
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(parent.childCount()):
                yield parent.child(j)

    def refresh_component_row(self, item: QTreeWidgetItem, component: AbsorberComponent) -> None:
        """Refresh one rendered component row from a current component."""
        with self.blocked_item_changed():
            self._row_renderer.refresh_model_row(item, component)

    def refresh_analysis_half_width_rows(
        self, project: SpectroscopyProject, affected_line_ids: tuple[str, ...]
    ) -> None:
        """Refresh rendered line-group half-width cells without rebuilding the tree."""
        affected = set(affected_line_ids)
        root = self._tree.invisibleRootItem()
        with self.blocked_item_changed():
            for index in range(root.childCount()):
                item = root.child(index)
                raw_ids = item.data(COL_ANALYSIS_HALF_WIDTH, ROLE_LINE_IDS)
                if not isinstance(raw_ids, tuple) or not affected.intersection(raw_ids):
                    continue
                lines = tuple(
                    project.absorption_lines[line_id]
                    for line_id in raw_ids
                    if isinstance(line_id, str) and line_id in project.absorption_lines
                )
                if lines:
                    self._row_renderer.refresh_line_analysis_half_width(item, lines)

    def render_groups(
        self,
        groups: tuple[tuple[AbsorptionLine, ...], ...],
        component_index: Mapping[str, AbsorberComponent],
    ) -> None:
        """Render grouped line rows and component child rows."""
        with self.blocked_item_changed():
            for display_index, group in enumerate(groups, start=1):
                parent_item = QTreeWidgetItem(self._tree)
                self._row_renderer.populate_multiplet_row(
                    parent_item, group, display_index, component_index
                )
                parent_item.setExpanded(True)

    def update_parameter_values(self, component_ids: tuple[str, ...]) -> None:
        """Refresh every rendered row whose component ID was affected."""
        affected_ids = set(component_ids)
        with self.blocked_item_changed():
            for item in self.iter_model_items():
                row_component = item.data(0, Qt.ItemDataRole.UserRole)
                if (
                    not isinstance(row_component, AbsorberComponent)
                    or row_component.id not in affected_ids
                ):
                    continue
                self._row_renderer.refresh_model_row(item, row_component)

    def focus_component(self, component_id: str) -> None:
        """Highlight the tree row corresponding to the component identifier."""
        if not component_id:
            return

        selection_model = self._tree.selectionModel()
        if selection_model is None:
            return

        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent_item = root.child(i)
            if parent_item is None:
                continue

            for j in range(parent_item.childCount()):
                child = parent_item.child(j)
                component = child.data(0, Qt.ItemDataRole.UserRole)
                if not isinstance(component, AbsorberComponent):
                    continue
                if component.id != component_id:
                    continue

                parent_item.setExpanded(True)

                index = self._tree.indexFromItem(child, 0)
                if not index.isValid():
                    return

                selection_flags = (
                    QItemSelectionModel.SelectionFlag.ClearAndSelect
                    | QItemSelectionModel.SelectionFlag.Rows
                )
                selection_model.select(index, selection_flags)
                self._tree.setCurrentIndex(index)
                self._tree.scrollToItem(child, QAbstractItemView.ScrollHint.PositionAtCenter)
                self._tree.setFocus(Qt.FocusReason.OtherFocusReason)
                return

    def select_component_for_line(
        self, line: AbsorptionLine, component: AbsorberComponent | None
    ) -> None:
        """Select and start editing a component row under a line row."""
        if component is None:
            return

        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent_item = root.child(i)
            line_data = parent_item.data(0, Qt.ItemDataRole.UserRole)
            if not isinstance(line_data, AbsorptionLine):
                continue
            if line_data.line_id != line.line_id:
                continue
            for j in range(parent_item.childCount()):
                child = parent_item.child(j)
                child_component = child.data(0, Qt.ItemDataRole.UserRole)
                if not isinstance(child_component, AbsorberComponent):
                    continue
                if child_component.id == component.id:
                    self._tree.setCurrentItem(child, COL_SPECIES)
                    self._tree.editItem(child, COL_SPECIES)
                    self._tree.scrollToItem(child, QAbstractItemView.ScrollHint.PositionAtCenter)
                    self._tree.setFocus(Qt.FocusReason.OtherFocusReason)
                    return

    def select_line_by_id(self, line_id: str) -> bool:
        """Select a line in the tree by its identifier."""
        if not line_id:
            return False

        root = self._tree.invisibleRootItem()
        target_item: QTreeWidgetItem | None = None
        for index in range(root.childCount()):
            item = root.child(index)
            line = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(line, AbsorptionLine) and line.line_id == line_id:
                target_item = item
                break

        if target_item is None:
            return False

        self._tree.blockSignals(True)
        self._tree.clearSelection()
        target_item.setSelected(True)
        self._tree.blockSignals(False)
        self._tree.scrollToItem(target_item, QAbstractItemView.ScrollHint.PositionAtCenter)
        self._on_selection_changed()
        return True

    def blocked_item_changed(self) -> AbstractContextManager[None]:
        """Return a guard that suppresses tree itemChanged handling."""
        return _ItemChangedBlocker(self._set_item_changed_suppressed)


class _ItemChangedBlocker(AbstractContextManager[None]):
    """Context manager that toggles item-changed suppression."""

    def __init__(self, set_suppressed: Callable[[bool], None]) -> None:
        self._set_suppressed = set_suppressed

    def __enter__(self) -> None:
        self._set_suppressed(True)

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self._set_suppressed(False)
