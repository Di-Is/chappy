"""Controller for optimize tree parameter cell styling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor

from chappy.core.components.absorber import AbsorberComponent
from chappy.gui.theme import Colors

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from PySide6.QtWidgets import QTreeWidgetItem

    from chappy.core.spectroscopy_project import SpectroscopyProject


def component_needs_optimization(
    project: SpectroscopyProject | None, component: AbsorberComponent
) -> bool:
    """Return whether any line linked to the component is stale."""
    if project is None:
        return False

    component_id = component.id
    if not component_id:
        return False

    return any(
        line.needs_optimization
        for line in project.absorption_lines.values()
        if component_id in line.model_ids
    )


@dataclass(frozen=True, slots=True)
class OptimizeTreeStyleColumns:
    """Column mapping required to style optimize parameter rows."""

    parameter_columns: Mapping[int, str]


class OptimizeTreeStylePort(Protocol):
    """Panel operations required by tree style updates."""

    def ensure_tree_covering_factor_parameter(self, component: AbsorberComponent) -> None:
        """Ensure the component has a covering factor parameter."""
        ...

    def tie_accent_index_for(
        self, component: AbsorberComponent, parameter_name: str
    ) -> int | None:
        """Return the tie-set accent palette index for a masked parameter cell, if tied."""
        ...


class OptimizeTreeStyleController:
    """Apply fixed-parameter and stale-component styles to optimize tree rows."""

    def __init__(self, *, columns: OptimizeTreeStyleColumns, port: OptimizeTreeStylePort) -> None:
        """Initialize the style controller.

        Args:
            columns: Parameter and error columns to style.
            port: Panel operation required before styling.
        """
        self._columns = columns
        self._port = port

        fixed_bg = QColor(Colors.WARNING)
        fixed_bg.setAlpha(110)
        self._fixed_parameter_brush = QBrush(fixed_bg)

        stale_bg = QColor(Colors.ERROR)
        stale_bg.setAlpha(90)
        self._stale_parameter_brush = QBrush(stale_bg)

        tie_accent_brushes: list[QBrush] = []
        for accent_color in Colors.TIE_ACCENT_COLORS:
            accent_bg = QColor(accent_color)
            accent_bg.setAlpha(70)
            tie_accent_brushes.append(QBrush(accent_bg))
        self._tie_accent_brushes: tuple[QBrush, ...] = tuple(tie_accent_brushes)

    def refresh_parameter_styles(
        self, *, items: Iterable[QTreeWidgetItem], project: SpectroscopyProject | None
    ) -> None:
        """Refresh all supplied component row styles."""
        for item in items:
            self.apply_parameter_styles(item, project)

    def apply_parameter_styles(
        self, item: QTreeWidgetItem, project: SpectroscopyProject | None
    ) -> None:
        """Apply parameter-related styles to one component row."""
        component = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(component, AbsorberComponent):
            return

        self._port.ensure_tree_covering_factor_parameter(component)
        is_stale = component_needs_optimization(project, component)

        empty_brush = QBrush()
        for column, param_name in self._columns.parameter_columns.items():
            param = component.parameters.get(param_name)
            if param is not None and param.fixed:
                item.setBackground(column, self._fixed_parameter_brush)
                continue

            if is_stale:
                item.setBackground(column, self._stale_parameter_brush)
                continue

            tie_index = self._port.tie_accent_index_for(component, param_name)
            if tie_index is not None:
                item.setBackground(
                    column, self._tie_accent_brushes[tie_index % len(self._tie_accent_brushes)]
                )
            else:
                item.setBackground(column, empty_brush)
