"""Controller interpreting optimize tree ``itemChanged`` edits."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt

from chappy.core.components.absorber import AbsorberComponent
from chappy.gui.modes.analysis.region_detail.tree.tree_columns import (
    ROLE_EDIT_KIND,
    TreeCellEditKind,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtWidgets import QTreeWidgetItem


def _is_rendered_value_cell_text(text: str) -> bool:
    """Return whether text carries formatting only the tree renderer produces.

    A tie-set label prefix (``[A] ...``) or an integrated uncertainty suffix
    (``... ± ...``) can only originate from the row renderer, never from a
    user-typed edit, since edits commit plain text through the delegate's
    setModelData.
    """
    return text.startswith("[") or "±" in text


class OptimizeTreeEditController:
    """Interpret one tree ``itemChanged`` edit and dispatch it to its handler."""

    def __init__(
        self,
        *,
        apply_parameter_value: Callable[[AbsorberComponent, str, float], bool],
        reset_component_parameter: Callable[[QTreeWidgetItem, int, AbsorberComponent, str], None],
        apply_line_analysis_half_width: Callable[[QTreeWidgetItem, int], None],
    ) -> None:
        """Initialize the controller.

        Args:
            apply_parameter_value: Applies a validated component parameter edit.
            reset_component_parameter: Restores a component parameter cell after a
                rejected or unparsable edit.
            apply_line_analysis_half_width: Applies one scientific half-width cell edit.
        """
        self._apply_parameter_value = apply_parameter_value
        self._reset_component_parameter = reset_component_parameter
        self._apply_line_analysis_half_width = apply_line_analysis_half_width

    def item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Interpret and dispatch one tree ``itemChanged`` edit."""
        raw_edit_kind = item.data(column, ROLE_EDIT_KIND)
        try:
            edit_kind = TreeCellEditKind(raw_edit_kind)
        except (TypeError, ValueError):
            edit_kind = TreeCellEditKind.NONE
        if edit_kind is TreeCellEditKind.LINE_ANALYSIS_HALF_WIDTH:
            self._apply_line_analysis_half_width(item, column)
            return
        if edit_kind is not TreeCellEditKind.COMPONENT_PARAMETER or not item.parent():
            return

        component = item.data(0, Qt.ItemDataRole.UserRole)
        param_name = item.data(column, Qt.ItemDataRole.UserRole)
        if not isinstance(component, AbsorberComponent) or not isinstance(param_name, str):
            return

        text = item.text(column).strip()
        if _is_rendered_value_cell_text(text):
            # This is a stale re-delivery of our own renderer output (tie label
            # prefix and/or rounded "value ± error" suffix), not a user edit.
            # Genuine edits always commit plain text through the delegate's
            # setModelData, so ignore it instead of resetting the row.
            return

        try:
            value = float(text)
        except ValueError:
            self._reset_component_parameter(item, column, component, param_name)
            return

        if not self._apply_parameter_value(component, param_name, value):
            self._reset_component_parameter(item, column, component, param_name)
